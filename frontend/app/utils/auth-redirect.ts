/** Accept app paths only, including their query and fragment. Never external URLs. */
export function internalRedirect(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/'
  // Reject browser URL normalization ambiguities, encoded separators and control bytes.
  if (
    value.includes('\\') ||
    [...value].some((char) => char.charCodeAt(0) <= 32 || char.charCodeAt(0) === 127) ||
    /%(?:2f|5c|0[0-9a-f]|1[0-9a-f]|7f)/i.test(value.split(/[?#]/)[0]!)
  )
    return '/'
  try {
    const url = new URL(value, 'https://admin.invalid')
    if (
      url.origin !== 'https://admin.invalid' ||
      url.pathname.startsWith('//') ||
      /^\/login\/?$/i.test(decodeURIComponent(url.pathname))
    )
      return '/'
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return '/'
  }
}

export function loginRedirect(target: string) {
  return { path: '/login', query: { redirect: internalRedirect(target) } }
}

// Fragments are not sent in HTTP requests. Browsers carry them across an SSR
// redirect; fold that fragment back into the intended path after login.
export function returnTarget(value: unknown, hash = ''): string {
  const target = internalRedirect(value)
  return internalRedirect(target.includes('#') ? target : `${target}${hash}`)
}

export function workspaceTarget(value: unknown, hash: string, isAdmin: boolean): string {
  const target = returnTarget(value, hash)
  return isAdmin || /^\/research(?:[/?#]|$)/.test(target) ? target : '/research'
}
