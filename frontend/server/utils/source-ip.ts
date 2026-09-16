import { isIP } from 'node:net'

// Only an explicitly trusted ingress may supply the single, overwritten X-Real-IP.
// Never consume an incoming X-Forwarded-For chain.
export function sourceIp(
  peer: string | undefined,
  realIp: string | undefined,
  trusted: string,
): string | undefined {
  if (!peer || !isIP(peer)) return undefined
  if (
    trusted
      .split(',')
      .map((value) => value.trim())
      .includes(peer) &&
    realIp &&
    isIP(realIp)
  )
    return realIp
  return peer
}
