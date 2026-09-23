/** Operator-owned XYZ configuration only; never interpolate entity/provider text. */
export function mapTileUrl(value: string): string | null {
  // One fixed HTTPS origin (or same-origin path), XYZ path, no credentials/query/fragment.
  if (value.length > 2048) return null
  const pattern =
    /^(?:https:\/\/[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]{1,5})?)?\/(?:[a-zA-Z0-9_-]+\/)*\{z\}\/\{x\}\/\{y\}\.(?:png|jpg|webp)$/
  return pattern.test(value) ? value : null
}

export function mapAttributionUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null
  } catch {
    return null
  }
}
