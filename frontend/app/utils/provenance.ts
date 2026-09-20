import type { ProvenanceView } from '#shared/sql-provenance'
export function provenanceRoute(
  path: string,
  content = false,
): { view: ProvenanceView; endpoint: string } | null {
  const fixed: Record<string, [ProvenanceView, string]> = {
    '/': ['dashboard', '/dashboard/summary'],
    '/quality': ['quality', '/dashboard/summary'],
    '/activity': ['activity', '/dashboard/activity'],
    '/findings': ['findings', '/findings'],
    '/checks': ['checks', '/check-runs'],
    '/geocoding': ['geocoding', '/geocode/requests'],
    '/marks': ['marks', '/record-marks'],
    '/graph': ['graph', '/graph'],
    '/statistics': content
      ? ['statistics.content', '/statistics/events/content']
      : ['statistics', '/statistics/entities'],
    '/notifications': ['notifications', '/notifications'],
    '/notifications/deliveries': ['deliveries', '/notification-deliveries'],
  }
  if (fixed[path]) return { view: fixed[path][0], endpoint: '/api/v1' + fixed[path][1] }
  const entity = path.match(
    /^\/(organizations|venues|spaces|events|users|images)(?:\/([0-9a-f-]{36}))?$/,
  )
  if (entity)
    return {
      view: (entity[1] + (entity[2] ? '.detail' : '')) as ProvenanceView,
      endpoint: '/api/v1' + path,
    }
  const queue = path.match(/^\/queues\/(partner_requests|team_invitations|user_activation)$/)
  if (queue)
    return {
      view: ('queues.' + queue[1]) as ProvenanceView,
      endpoint: '/api/v1/work-queues/' + queue[1],
    }
  const detail = path.match(
    /^\/(geocoding|marks|notifications|notifications\/deliveries)\/([0-9a-f-]{36})$/,
  )
  if (detail) {
    const map: Record<string, [ProvenanceView, string]> = {
      geocoding: ['geocoding.detail', 'geocode/requests'],
      marks: ['marks.detail', 'record-marks'],
      notifications: ['notifications.detail', 'notifications'],
      'notifications/deliveries': ['deliveries.detail', 'notification-deliveries'],
    }
    const target = map[detail[1]!]!
    return { view: target[0], endpoint: '/api/v1/' + target[1] + '/' + detail[2] }
  }
  return null
}
