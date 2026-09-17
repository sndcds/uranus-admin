import type { z } from '#shared/zod'
import {
  periodSchema,
  statisticsPeriodSchema,
  sharedPeriodSchema,
  type SharedPeriod,
} from '#shared/contracts'

export { sharedPeriodSchema, type SharedPeriod } from '#shared/contracts'
export const sharedPeriodLabels: Record<SharedPeriod, string> = {
  today: 'Heute',
  '24h': 'Letzte 24 Stunden',
  '7d': 'Letzte 7 Tage',
  '30d': 'Letzte 30 Tage',
  '90d': 'Letzte 90 Tage',
}
export const pagePeriods = {
  entities: sharedPeriodSchema,
  eventContent: sharedPeriodSchema,
  dashboard: periodSchema,
  activity: periodSchema,
  statistics: statisticsPeriodSchema.exclude(['custom']),
}
export type PeriodPage = keyof typeof pagePeriods
export type PagePeriod<P extends PeriodPage> = z.infer<(typeof pagePeriods)[P]>
export const pageDefaultPeriod = {
  dashboard: '24h',
  activity: '24h',
  statistics: '24h',
  entities: '24h',
  eventContent: '24h',
} as const
export function supportsPeriod<P extends PeriodPage>(
  page: P,
  value: unknown,
): value is PagePeriod<P> {
  return pagePeriods[page].safeParse(value).success
}
export function resolvePeriod<P extends PeriodPage>(page: P, preferred: unknown): PagePeriod<P> {
  return supportsPeriod(page, preferred) ? preferred : (pageDefaultPeriod[page] as PagePeriod<P>)
}
export function periodOptions<P extends PeriodPage>(page: P) {
  return Object.fromEntries(
    pagePeriods[page].options.map((value) => [value, sharedPeriodLabels[value]]),
  ) as Record<PagePeriod<P>, string>
}
export const dashboardPeriods = periodOptions('dashboard')
export const activityPeriods = periodOptions('activity')
export const statisticsPeriods = periodOptions('statistics')

export const entityPeriods = periodOptions('entities')

export const eventContentPeriods = { all: 'Alle', ...periodOptions('eventContent') }
