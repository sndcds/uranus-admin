/** Elapsed time includes queue wait: started_at is assigned when the job is enqueued. */
export function checkDuration(startedAt: string, finishedAt: string | null): string | null {
  if (!finishedAt) return null
  const milliseconds = Date.parse(finishedAt) - Date.parse(startedAt)
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return null
  const seconds = Math.floor(milliseconds / 1000)
  if (seconds < 60) return `${seconds} s`
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}
