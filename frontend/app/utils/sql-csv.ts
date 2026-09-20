/** Export only the rows already returned by the bounded query. */
export function sqlCsv(columns: string[], rows: Record<string, unknown>[]): string {
  function cell(value: unknown): string {
    let text =
      value === null || value === undefined
        ? ''
        : typeof value === 'string'
          ? value
          : JSON.stringify(value)
    // Treat source strings as spreadsheet data, including whitespace-prefixed formulas.
    if (typeof value === 'string' && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  return (
    [
      columns.map(cell).join(','),
      ...rows.map((row) => columns.map((column) => cell(row[column])).join(',')),
    ].join('\r\n') + '\r\n'
  )
}
