import WebSocket from 'ws'
import { consoleClientSchema, consoleServerSchema, consolePath } from '#shared/sql-console'
import { consoleCookie, openConsoleUpstream } from '../../../../../utils/sql-console-proxy'

const upstreams = new Map<string, WebSocket>()
const reserved = new Set<WebSocket>()
let pending = 0
export default defineWebSocketHandler({
  async upgrade(request) {
    const url = new URL(request.url, 'http://local.invalid')
    const cookie = consoleCookie(request.headers.get('cookie'), import.meta.dev)
    const origin = request.headers.get('origin')
    if (
      url.pathname !== consolePath ||
      url.search ||
      !cookie ||
      !origin ||
      request.headers.has('authorization')
    )
      return new Response(null, { status: 403 })
    if (pending + reserved.size >= 32) return new Response(null, { status: 503 })
    if (!request.context) return new Response(null, { status: 503 })
    pending++
    try {
      // Backend verifies the exact AUTH_PUBLIC_ORIGIN and the current session/grant
      // before this browser handshake is accepted. No Host/forwarded-header trust.
      const upstream = await openConsoleUpstream(useRuntimeConfig().adminApiBase, cookie, origin)
      reserved.add(upstream)
      upstream.once('close', () => reserved.delete(upstream))
      request.context.upstream = upstream
      request.context.openTimer = setTimeout(() => upstream.terminate(), 2000)
    } catch {
      return new Response(null, { status: 503 })
    } finally {
      pending--
    }
  },
  open(peer) {
    const upstream = peer.context.upstream
    if (!(upstream instanceof WebSocket)) {
      peer.close(1011)
      return
    }
    clearTimeout(peer.context.openTimer as ReturnType<typeof setTimeout>)
    upstreams.set(peer.id, upstream)
    upstream.on('message', (data, binary) => {
      try {
        if (
          binary ||
          Buffer.byteLength(data.toString()) > 70 * 1024 ||
          (peer.websocket.bufferedAmount ?? 0) > 70 * 1024
        )
          throw new Error('Invalid frame')
        const message = consoleServerSchema.parse(JSON.parse(data.toString()))
        peer.send(JSON.stringify(message))
      } catch {
        upstream.terminate()
        peer.close(1008)
      }
    })
    upstream.on('close', (code) => {
      upstreams.delete(peer.id)
      peer.close([4401, 4403, 1000].includes(code) ? code : 1011)
    })
    upstream.on('error', () => {
      upstreams.delete(peer.id)
      peer.close(1011)
    })
  },
  message(peer, frame) {
    const upstream = upstreams.get(peer.id)
    try {
      if (
        !upstream ||
        upstream.readyState !== WebSocket.OPEN ||
        frame.uint8Array().byteLength > 200_000 ||
        upstream.bufferedAmount > 200_000
      )
        throw new Error('Invalid frame')
      upstream.send(JSON.stringify(consoleClientSchema.parse(frame.json())))
    } catch {
      upstream?.terminate()
      peer.close(1008)
    }
  },
  close(peer) {
    upstreams.get(peer.id)?.terminate()
    upstreams.delete(peer.id)
  },
  error(peer) {
    upstreams.get(peer.id)?.terminate()
    upstreams.delete(peer.id)
  },
})
