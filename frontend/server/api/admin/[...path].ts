import { forwardAdminRequest } from '../../utils/admin-proxy'

export default defineEventHandler(async (event) => {
  setHeader(event, 'Cache-Control', 'private, no-store')
  setHeader(event, 'Vary', 'Authorization, Cookie, Origin')
  const config = useRuntimeConfig(event)
  let body: unknown
  if (event.method === 'PATCH' || event.method === 'POST') {
    try {
      const raw = await readRawBody(event)
      if (raw && Buffer.byteLength(raw) > 32768) throw new Error('Invalid body')
      body = raw ? JSON.parse(raw) : undefined
    } catch {
      setResponseStatus(event, 422)
      return { error: { code: 'invalid_input', message: 'Invalid request body.' } }
    }
  }
  const cookieName = import.meta.dev ? 'admin_session' : '__Host-admin_session'
  const sessionToken = getCookie(event, cookieName)
  const result = await forwardAdminRequest(
    {
      path: `/${getRouterParam(event, 'path') ?? ''}`,
      method: event.method,
      body,
      query: getRequestURL(event).searchParams,
      authorization: getHeader(event, 'authorization'),
      sessionCookie: sessionToken ? `${cookieName}=${sessionToken}` : undefined,
      origin: getHeader(event, 'origin'),
      csrf: getHeader(event, 'x-admin-csrf'),
    },
    config.adminApiBase,
  )
  setResponseStatus(event, result.status)
  if (result.status === 401) setHeader(event, 'WWW-Authenticate', 'Bearer')
  if (result.status === 405) setHeader(event, 'Allow', 'GET')
  for (const cookie of result.setCookies ?? []) appendResponseHeader(event, 'Set-Cookie', cookie)
  return result.body
})
