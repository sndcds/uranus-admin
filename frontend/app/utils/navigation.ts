/** Descendants belong to their section; spaces share the places navigation. */
export function isNavigationActive(path: string, target: string): boolean {
  if (target === '/') return path === '/'
  if (target === '/venues' && (path === '/spaces' || path.startsWith('/spaces/'))) return true
  return path === target || path.startsWith(`${target}/`)
}

export const adminNavigationItems = [
  { label: 'Übersicht', keywords: 'Dashboard', icon: 'home', to: '/' },
  { label: 'Inbox', icon: 'list', to: '/inbox' },
  { label: 'Partneranfragen', icon: 'organization', to: '/queues/partner_requests' },
  { label: 'Einladungen', icon: 'users', to: '/queues/team_invitations' },
  { label: 'Aktivierungen', icon: 'users', to: '/queues/user_activation' },
  {
    label: 'Social Publishing',
    keywords: 'Posts Targets Publications Scheduling',
    icon: 'calendar',
    to: '/social-publishing',
  },
  { label: 'Benachrichtigungen', icon: 'list', to: '/notifications' },
  { label: 'Prüfläufe', icon: 'history', to: '/checks' },
  { label: 'Aktivität', icon: 'history', to: '/activity' },
  { label: 'Arbeitsliste', icon: 'list', to: '/findings' },
  { label: 'Markierungen', icon: 'list', to: '/marks' },
  { label: 'Veranstaltungen', icon: 'calendar', to: '/events' },
  { label: 'Orte & Räume', icon: 'pin', to: '/venues' },
  { label: 'Organisationen', icon: 'organization', to: '/organizations' },
  { label: 'Benutzer & Teams', icon: 'users', to: '/users' },
  { label: 'Bilder', icon: 'image', to: '/images' },
  { label: 'Beziehungsgraph', icon: 'graph', to: '/graph' },
  { label: 'SQL Console', icon: 'code', to: '/sql' },
  { label: 'Statistiken', icon: 'chart', to: '/statistics' },
  { label: 'Datenqualität', icon: 'quality', to: '/quality' },
  { label: 'Standortvorschläge', icon: 'pin', to: '/geocoding', keywords: 'Geocoding' },
] as const
