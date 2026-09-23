// Controlled E2E backend only. Never imported by the Nuxt application.
import http from 'node:http'
import { WebSocketServer } from 'ws'
import { randomBytes } from 'node:crypto'
import { summary, findings } from './api.ts'
import { geoArea, geoSearchItem } from './geo.ts'

const sessions = new Map()
const production = process.env.TEST_PRODUCTION === '1'
const cookieName = production ? '__Host-admin_session' : 'admin_session'
const attributes = `Path=/; HttpOnly; SameSite=Strict${production ? '; Secure' : ''}`
const server = http
  .createServer(async (request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.setHeader('Cache-Control', 'private, no-store')
    const send = (status, body) => {
      response.writeHead(status)
      response.end(JSON.stringify(body))
    }
    const deny = (status, code) =>
      send(status, { error: { code, message: 'Synthetic test failure' } })
    const path = new URL(request.url, 'http://127.0.0.1:31902').pathname
    if (path === '/health') return send(200, { status: 'ok' })
    const token = (request.headers.cookie ?? '')
      .split('; ')
      .find((part) => part.startsWith(`${cookieName}=`))
      ?.slice(cookieName.length + 1)
    if (request.method === 'POST' && path.startsWith('/auth/')) {
      if (
        request.headers.origin !== 'http://127.0.0.1:3100' ||
        request.headers['x-admin-csrf'] !== '1'
      )
        return deny(403, 'csrf_rejected')
      if (path === '/auth/logout') {
        sessions.delete(token)
        response.setHeader('Set-Cookie', `${cookieName}=; ${attributes}; Max-Age=0`)
        return send(200, { status: 'ok' })
      }
      if (path === '/auth/login') {
        let body = ''
        for await (const chunk of request) body += chunk
        const credentials = JSON.parse(body)
        if (
          !['operator', 'ordinary'].includes(credentials.login) ||
          credentials.password !== 'test-only-password'
        )
          return deny(401, 'invalid_credentials')
        const next = randomBytes(32).toString('base64url')
        const principal = {
          subject:
            credentials.login === 'operator'
              ? 'admin:00000000-0000-4000-8000-000000000800'
              : 'admin:00000000-0000-4000-8000-000000000801',
          system_admin: credentials.login === 'operator',
        }
        sessions.delete(token)
        sessions.set(next, principal)
        response.setHeader('Set-Cookie', `${cookieName}=${next}; ${attributes}`)
        return send(200, principal)
      }
    }
    const principal = sessions.get(token)
    if (!principal) return deny(401, token ? 'invalid_credentials' : 'authentication_required')
    if (!principal.system_admin) return deny(403, 'admin_access_denied')
    if (
      /^\/api\/v1\/(?:notification-deliveries|geocode\/requests)\/[0-9a-f-]+\/retry$/.test(path) &&
      request.method === 'POST'
    ) {
      if (
        request.headers.origin !== 'http://127.0.0.1:3100' ||
        request.headers['x-admin-csrf'] !== '1'
      )
        return deny(403, 'csrf_rejected')
      return deny(
        409,
        path.includes('/geocode/') ? 'geocode_no_longer_needed' : 'notification_retry_obsolete',
      )
    }
    if (path === '/api/v1/geo/areas/search') return send(200, { items: [geoSearchItem] })
    if (path === `/api/v1/geo/areas/${geoArea.id}`) return send(200, geoArea)
    if (path.startsWith('/api/v1/geo/areas/')) return deny(404, 'geo_scope_not_found')
    if (path === '/api/v1/geo/areas' && request.method === 'POST') {
      if (
        request.headers.origin !== 'http://127.0.0.1:3100' ||
        request.headers['x-admin-csrf'] !== '1'
      )
        return deny(403, 'csrf_rejected')
      return send(200, geoArea)
    }
    if (path === '/auth/session') return send(200, principal)
    if (path === '/api/v1/admins')
      return send(200, {
        items: [{ id: '00000000-0000-4000-8000-000000000800', login: 'operator' }],
        admin_timezone: 'Europe/Berlin',
      })
    if (path === '/api/v1/assignments' && request.method === 'GET') return send(200, null)
    if (path === '/api/v1/dashboard/summary') return send(200, summary)
    if (path === '/api/v1/findings') return send(200, findings)
    return deny(404, 'route_not_allowed')
  })
  .listen(31902, '127.0.0.1')

// Controlled protocol fixture: exercises Nitro relay, never claims DB execution.
const wss = new WebSocketServer({ noServer: true, maxPayload: 200000 })
server.on('upgrade', (request, socket, head) => {
  const token = (request.headers.cookie ?? '')
    .split('; ')
    .find((part) => part.startsWith(`${cookieName}=`))
    ?.slice(cookieName.length + 1)
  if (
    request.url !== '/api/v1/sql-console/ws' ||
    request.headers.origin !== 'http://127.0.0.1:3100' ||
    !sessions.get(token)?.system_admin
  ) {
    socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n')
    return
  }
  wss.handleUpgrade(request, socket, head, (ws) => wss.emit('connection', ws))
})
wss.on('connection', (socket) => {
  let active = null
  socket.on('message', (data) => {
    const message = JSON.parse(data.toString())
    const send = (body) =>
      socket.send(JSON.stringify({ v: 1, request_id: message.request_id, ...body }))
    if (message.type === 'cancel') {
      active = null
      send({ type: 'cancelled', duration_ms: 24 })
      return
    }
    if (message.type === 'ack') {
      if (active) send({ type: 'complete', row_count: 2, truncated: false, duration_ms: 14 })
      active = null
      return
    }
    if (message.type !== 'execute') return
    active = message.request_id
    send({ type: 'started' })
    if (message.sql.includes('fixture_running')) return
    if (message.sql.includes('fixture_error')) {
      send({ type: 'error', code: 'syntax_error', position: 8, duration_ms: 2 })
      active = null
      return
    }
    send({
      type: 'columns',
      columns: ['uuid', 'event_uuid', 'start_date', 'start_time', 'end_date', 'end_time'],
    })
    send({
      type: 'rows',
      batch: 1,
      rows: [
        {
          uuid: '00000000-0000-4000-8000-000000000030',
          event_uuid: '00000000-0000-4000-8000-000000000031',
          start_date: '2026-10-12',
          start_time: '18:00:00',
          end_date: '2026-10-11',
          end_time: '17:00:00',
        },
        {
          uuid: '00000000-0000-4000-8000-000000000032',
          event_uuid: '00000000-0000-4000-8000-000000000033',
          start_date: '2026-10-13',
          start_time: '19:00:00',
          end_date: null,
          end_time: null,
        },
      ],
    })
  })
})
