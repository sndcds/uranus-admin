import { describe, expect, it } from 'vitest'
import { sourceIp } from '../../server/utils/source-ip'

describe('trusted ingress source', () => {
  it('ignores forwarded input from untrusted peers', () => {
    expect(sourceIp('192.0.2.1', '198.51.100.1', '')).toBe('192.0.2.1')
  })
  it('accepts one IP only from an explicitly trusted peer', () => {
    expect(sourceIp('127.0.0.1', '198.51.100.1', '127.0.0.1')).toBe('198.51.100.1')
    expect(sourceIp('127.0.0.1', '198.51.100.1, 192.0.2.1', '127.0.0.1')).toBe('127.0.0.1')
    expect(sourceIp(undefined, '198.51.100.1', '*')).toBeUndefined()
  })
})
