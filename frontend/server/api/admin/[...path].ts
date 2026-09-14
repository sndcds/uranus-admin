import { forwardAdminRequest } from '../../utils/admin-proxy'

export default defineEventHandler(async (event) => {
  setHeader(event, 'Cache-Control', 'private, no-store')
  setHeader(event, 'Vary', 'Authorization')
  const config = useRuntimeConfig(event)
  const result = await forwardAdminRequest(
    {
      path: `/${getRouterParam(event, 'path') ?? ''}`,
      method: event.method,
      query: getRequestURL(event).searchParams,
      authorization: getHeader(event, 'authorization'),
    },
    config.adminApiBase,
  )
  setResponseStatus(event, result.status)
  if (result.status === 401) setHeader(event, 'WWW-Authenticate', 'Bearer')
  if (result.status === 405) setHeader(event, 'Allow', 'GET')
  return result.body
})
