import WebSocket from 'ws'

export function consoleUpstream(base: string): URL {
  const url = new URL(base)
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== '/'
  )
    throw new Error('Invalid upstream configuration')
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/api/v1/sql-console/ws'
  return url
}
export function consoleCookie(header: string | null, development: boolean): string | null {
  const name = development ? 'admin_session' : '__Host-admin_session'
  const matches = (header ?? '')
    .split(';')
    .map((value) => value.trim())
    .filter((value) => value.startsWith(`${name}=`))
  return matches.length === 1 && new RegExp(`^${name}=[A-Za-z0-9_-]{43}$`).test(matches[0]!)
    ? matches[0]!
    : null
}
export async function openConsoleUpstream(
  base: string,
  cookie: string,
  origin: string,
): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(consoleUpstream(base), {
      headers: { Cookie: cookie, Origin: origin },
      followRedirects: false,
      handshakeTimeout: 5000,
      maxPayload: 70 * 1024,
      perMessageDeflate: false,
    })
    socket.once('open', () => resolve(socket))
    socket.on('error', () => {
      socket.terminate()
      reject(new Error('Console unavailable'))
    })
    socket.once('unexpected-response', (_request, response) => {
      response.resume()
      socket.terminate()
      reject(new Error('Console unavailable'))
    })
  })
}
