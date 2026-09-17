// Controlled E2E backend only. Never imported by the Nuxt application.
import http from 'node:http'
import { randomBytes } from 'node:crypto'
import { summary, findings } from './api.ts'

const sessions = new Map()
const production = process.env.TEST_PRODUCTION === '1'
const cookieName = production ? '__Host-admin_session' : 'admin_session'
const attributes = `Path=/; HttpOnly; SameSite=Strict${production ? '; Secure' : ''}`
http
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
          subject: `admin:${randomBytes(16).toString('hex')}`,
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
    if (path === '/auth/session') return send(200, principal)
    if (path === '/api/v1/dashboard/summary') return send(200, summary)
    if (path === '/api/v1/findings') return send(200, findings)
    return deny(404, 'route_not_allowed')
  })
  .listen(31902, '127.0.0.1')
