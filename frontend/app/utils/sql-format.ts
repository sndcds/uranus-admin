/** Lazy presentation only: never used by the API client or execution handlers. */
export async function formatSql(sql: string): Promise<string> {
  try {
    const { formatPostgresql } = await import('./sql-formatter')
    return formatPostgresql(sql)
  } catch {
    return sql
  }
}
