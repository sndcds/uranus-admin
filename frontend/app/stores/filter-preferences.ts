import { defineStore } from 'pinia'
import { z } from '#shared/zod'
import {
  entityTypeSchema,
  graphEntityTypeSchema,
  graphRelationTypeSchema,
  statisticsEntitySchema,
  statisticsIntervalSchema,
  temporalFilterSchema,
  type EntitySection,
} from '#shared/contracts'
import {
  sharedPeriodSchema,
  resolvePeriod,
  supportsPeriod,
  type SharedPeriod,
  type PeriodPage,
} from '../utils/periods'

const q = z.string().max(120).default('')
const temporal = temporalFilterSchema.or(z.literal('')).default('')
const period = sharedPeriodSchema.or(z.literal('')).default('')
const entitySchemas = {
  events: z.object({
    q,
    period,
    status: z
      .enum(['', 'released', 'draft', 'review', 'cancelled', 'deferred', 'rescheduled'])
      .default(''),
    temporal,
  }),
  users: z.object({ q, period, status: z.enum(['', 'active', 'inactive']).default('') }),
  organizations: z.object({ q, temporal, period }),
  venues: z.object({ q, temporal, period }),
  spaces: z.object({ q, temporal, period }),
  images: z.object({ q, period }),
}
export type EntityPreferences = { [S in EntitySection]: z.infer<(typeof entitySchemas)[S]> }
const defaults = () => ({
  sharedPeriod: '24h' as SharedPeriod,
  sharedPeriodChosen: false,
  entityPeriodsSet: {
    events: false,
    users: false,
    organizations: false,
    venues: false,
    spaces: false,
    images: false,
  },
  entities: {
    events: entitySchemas.events.parse({}),
    users: entitySchemas.users.parse({}),
    organizations: entitySchemas.organizations.parse({}),
    venues: entitySchemas.venues.parse({}),
    spaces: entitySchemas.spaces.parse({}),
    images: entitySchemas.images.parse({}),
  },
  activity: {
    entityType: '' as z.infer<typeof entityTypeSchema> | '',
    period: resolvePeriod('activity', '24h'),
  },
  statistics: {
    period: resolvePeriod('statistics', '24h'),
    interval: 'auto' as z.infer<typeof statisticsIntervalSchema> | 'auto',
    compare: false,
    selectedTypes: [...statisticsEntitySchema.options],
  },
  graph: {
    entityType: '' as z.infer<typeof graphEntityTypeSchema> | '',
    relationType: '' as z.infer<typeof graphRelationTypeSchema> | '',
    organization: '',
    depth: 2,
  },
})
export const useFilterPreferencesStore = defineStore('filter-preferences', {
  state: defaults,
  actions: {
    resetAll() {
      this.$reset()
    },
    setSharedPeriod(value: unknown) {
      const parsed = sharedPeriodSchema.safeParse(value)
      if (parsed.success) {
        this.sharedPeriod = parsed.data
        this.sharedPeriodChosen = true
      }
    },
    resolvePeriodForPage<P extends PeriodPage>(page: P) {
      return resolvePeriod(page, this.sharedPeriod)
    },
    hydratePeriod(page: PeriodPage, value: unknown) {
      if (!supportsPeriod(page, value)) return
      this.setSharedPeriod(value)
      if (page === 'activity') this.activity.period = resolvePeriod('activity', value)
      if (page === 'statistics') this.statistics.period = resolvePeriod('statistics', value)
    },
    commitEntityFilters<S extends EntitySection>(section: S, value: EntityPreferences[S]) {
      this.hydrateEntity(section, value)
    },
    entityDefaults(section: EntitySection) {
      if (!this.entityPeriodsSet[section] && this.sharedPeriodChosen) {
        this.entities[section].period = this.sharedPeriod
        this.entityPeriodsSet[section] = true
      }
      return this.entities[section]
    },
    hydrateEntity(section: EntitySection, query: Record<string, unknown>, publishPeriod = true) {
      const parsed = entitySchemas[section].safeParse(query)
      // Invalid URL values remain visible as API validation errors, never as preferences.
      if (parsed.success) {
        Object.assign(this.entities, { [section]: parsed.data })
        this.entityPeriodsSet[section] = true
        if (publishPeriod && parsed.data.period) this.setSharedPeriod(parsed.data.period)
      }
    },
    resetEntity(section: EntitySection) {
      this.entityPeriodsSet[section] = true
      Object.assign(this.entities, { [section]: entitySchemas[section].parse({}) })
    },
    hydrateActivity(query: Record<string, unknown>) {
      const type = entityTypeSchema.or(z.literal('')).safeParse(query.entity_type ?? '')
      if (type.success) this.activity.entityType = type.data
      if (!query.from_at && !query.to_at && query.timestamp_state !== 'unknown')
        this.hydratePeriod('activity', query.period)
    },
    hydrateStatistics(query: Record<string, unknown>, previous?: Record<string, unknown>) {
      if (!query.from_at && !query.to_at && (!previous || query.period !== previous.period))
        this.hydratePeriod('statistics', query.period)
      const interval = statisticsIntervalSchema
        .or(z.literal('auto'))
        .safeParse(query.interval ?? 'auto')
      if (interval.success) this.statistics.interval = interval.data
      if (query.compare === undefined || query.compare === 'previous')
        this.statistics.compare = query.compare === 'previous'
    },
    hydrateGraph(query: Record<string, unknown>) {
      const entity = graphEntityTypeSchema.or(z.literal('')).safeParse(query.entity_type ?? '')
      const relation = graphRelationTypeSchema
        .or(z.literal(''))
        .safeParse(query.relation_type ?? '')
      const depth = z.coerce
        .number()
        .int()
        .min(1)
        .max(3)
        .safeParse(query.depth ?? 2)
      if (entity.success) this.graph.entityType = entity.data
      if (relation.success) this.graph.relationType = relation.data
      if (depth.success) this.graph.depth = depth.data
    },
  },
})
