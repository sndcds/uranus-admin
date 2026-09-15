// @vitest-environment node
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { expect, it, vi } from 'vitest'
import { summary, findings } from '../fixtures/api'

it('configures Zod before schema construction and parsing without probing Function', async () => {
  vi.resetModules()
  const codegen = vi.spyOn(globalThis, 'Function').mockImplementation(() => {
    throw new EvalError('Code generation forbidden by CSP')
  })
  try {
    // Import the actual schema entry point, not the bootstrap first: test ordering too.
    const { summarySchema, findingPageSchema } = await import('../../shared/contracts')
    const { z } = await import('../../shared/zod')
    expect(z.config().jitless).toBe(true)
    expect(summarySchema.safeParse(summary).success).toBe(true)
    expect(findingPageSchema.safeParse(findings).success).toBe(true)
    expect(summarySchema.safeParse({ ...summary, new_records: {} }).success).toBe(false)
    // Zod catches a failed capability probe; successful parsing alone would miss it.
    expect(codegen).not.toHaveBeenCalled()
  } finally {
    codegen.mockRestore()
  }
})

it('keeps application Zod imports behind the bootstrap and forbids compiler opt-ins', async () => {
  const root = fileURLToPath(new URL('../../', import.meta.url))
  for (const directory of ['app', 'shared', 'server']) {
    const files = await readdir(`${root}/${directory}`, { recursive: true })
    for (const file of files.filter((name) => /\.(?:[cm]?[jt]sx?|vue)$/.test(name))) {
      const path = `${directory}/${file}`
      const source = await readFile(`${root}/${path}`, 'utf8')
      expect(source, path).not.toMatch(/['"]zod\/compile(?:\/[^'"]*)?['"]/)
      expect(source, path).not.toMatch(/(?:\.\s*|\[\s*['"])(?:compile|withParser)\b/)
      expect(source, path).not.toMatch(/\bjitless\s*:\s*false\b/)
      if (path !== 'shared/zod.ts') {
        // Includes named/namespace imports, re-exports and dynamic imports/requires.
        expect(source, path).not.toMatch(/['"]zod(?:\/[^'"]*)?['"]/)
      }
    }
  }
})
