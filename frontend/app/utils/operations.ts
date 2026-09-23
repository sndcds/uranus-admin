/** Presentation only: callers supply verified contract values and domain labels. */
export type OperationValue = string | number | boolean | null | undefined
export type OperationTone = 'neutral' | 'info' | 'success' | 'warning' | 'error'
export interface CompactFact {
  label: string
  value: OperationValue
  metadata?: string
  tone?: OperationTone
}
export interface TechnicalFact extends CompactFact {
  copyable?: boolean
  mono?: boolean
}
export const operationTones: Record<OperationTone, string> = {
  neutral: 'text-slate-900',
  info: 'text-blue-700',
  success: 'text-emerald-800',
  warning: 'text-amber-800',
  error: 'text-rose-700',
}
export function hasOperationValue(value: unknown): boolean {
  return (
    (typeof value === 'string' && value.trim().length > 0) ||
    (typeof value === 'number' && Number.isFinite(value)) ||
    typeof value === 'boolean'
  )
}
export function operationValue(value: unknown): string {
  if (!hasOperationValue(value)) return 'Nicht verfügbar'
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein'
  return String(value)
}
