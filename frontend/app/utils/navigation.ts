/** Descendants belong to their section; spaces share the places navigation. */
export function isNavigationActive(path: string, target: string): boolean {
  if (target === '/') return path === '/'
  if (target === '/venues' && (path === '/spaces' || path.startsWith('/spaces/'))) return true
  return path === target || path.startsWith(`${target}/`)
}
