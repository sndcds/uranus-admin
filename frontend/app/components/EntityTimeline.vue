<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TimelineEntityType, TimelineItem } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { qualityRuleLabel } from '~/utils/quality'
import { adminTimeZone, dateTime } from '~/utils/presentation'

const props = defineProps<{
  entityType: TimelineEntityType
  entityKey: string
  compact?: boolean
}>()
const { $adminApi } = useNuxtApp()
const items = ref<TimelineItem[]>([])
const cursor = ref<string | null>(null)
const hasMore = ref(false)
const loading = ref(false)
const error = ref<ApiFailure | null>(null)
let generation = 0

const iconByKind = {
  source_created: 'database',
  source_updated: 'database',
  finding_detected: 'warning',
  finding_reviewed: 'quality',
  finding_reopened: 'refresh',
  finding_resolved: 'quality',
  mark_created: 'history',
  mark_updated: 'history',
  mark_completed: 'history',
  mark_reopened: 'history',
  assignment_created: 'users',
  assignment_snoozed: 'clock',
  assignment_unsnoozed: 'refresh',
  assignment_updated: 'users',
  assignment_completed: 'quality',
  assignment_reopened: 'history',
  assignment_cancelled: 'close',
  notification_delivery: 'mail',
  url_check: 'search',
  geocode_request: 'pin',
  geocode_result: 'pin',
  team_invitation: 'users',
  partner_request: 'partner',
} as const satisfies Record<TimelineItem['kind'], string>

async function load(reset: boolean) {
  const request = ++generation
  loading.value = true
  error.value = null
  if (reset) {
    items.value = []
    cursor.value = null
    hasMore.value = false
  }
  try {
    const page = await $adminApi.timeline(
      props.entityType,
      props.entityKey,
      reset ? undefined : (cursor.value ?? undefined),
    )
    if (request !== generation) return
    const known = new Set(items.value.map((item) => item.id))
    items.value = reset
      ? page.items
      : [...items.value, ...page.items.filter((item) => !known.has(item.id))]
    cursor.value = page.cursor_pagination.next_cursor
    hasMore.value = page.cursor_pagination.has_more
  } catch (cause) {
    if (request === generation) error.value = asFailure(cause)
  } finally {
    if (request === generation) loading.value = false
  }
}

onMounted(() => load(true))
watch(
  () => [props.entityType, props.entityKey],
  () => load(true),
)
onBeforeUnmount(() => {
  generation++
})
</script>

<template>
  <section
    class="space-y-3"
    :class="{ 'timeline-compact': compact }"
    aria-labelledby="entity-timeline-heading"
  >
    <SectionHeader
      title-id="entity-timeline-heading"
      title="Verlauf"
      description="Belegte Quell- und Admin-Ereignisse, neueste zuerst."
    />
    <p v-if="items.some((item) => item.kind === 'source_updated')" class="operations-meta">
      Quelländerungen belegen den letzten Änderungszeitpunkt. Frühere Feldwerte und ein
      Vorher-/Nachher-Vergleich sind nicht verfügbar.
    </p>
    <RequestState
      :loading="loading"
      :error="error"
      :has-data="items.length > 0"
      @retry="load(items.length === 0)"
    />
    <DataListShell v-if="items.length" as="ul" aria-label="Datensatzverlauf">
      <li v-for="item in items" :key="item.id" class="data-row flex gap-3">
        <span
          class="timeline-icon mt-0.5 flex shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
          :class="compact ? 'h-6 w-6' : 'h-8 w-8'"
        >
          <AppIcon :name="iconByKind[item.kind]" :size="16" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h4 class="text-sm font-semibold text-slate-900">{{ item.title }}</h4>
            <time
              class="text-xs text-slate-500"
              :datetime="item.occurred_at"
              :title="`${dateTime(item.occurred_at)} (${adminTimeZone})`"
            >
              {{ dateTime(item.occurred_at) }}
            </time>
          </div>
          <p
            v-if="item.summary"
            class="timeline-summary whitespace-pre-line text-slate-700"
            :class="compact ? 'text-xs leading-5' : 'mt-1 text-sm'"
          >
            {{ item.summary }}
          </p>
          <CompactFacts
            v-if="
              item.metadata.field ||
              item.metadata.rule ||
              item.metadata.http_status ||
              item.metadata.generation ||
              item.metadata.score != null
            "
            class="mt-2"
            missing="omit"
            :items="[
              { label: 'Betroffenes Feld', value: item.metadata.field },
              {
                label: 'Prüfregel',
                value: item.metadata.rule ? qualityRuleLabel(item.metadata.rule) : null,
              },
              { label: 'HTTP-Status', value: item.metadata.http_status },
              { label: 'Prüfgeneration', value: item.metadata.generation },
              {
                label: 'Übereinstimmung',
                value:
                  item.metadata.score == null ? null : `${Math.round(item.metadata.score * 100)} %`,
              },
            ]"
          />
          <div
            v-if="item.metadata.severity || item.actor || item.href"
            class="timeline-meta flex flex-wrap items-center gap-2 text-xs text-slate-500"
            :class="compact ? 'mt-1' : 'mt-2'"
          >
            <SeverityBadge v-if="item.metadata.severity" :severity="item.metadata.severity" />
            <span v-if="item.actor">{{ item.actor }}</span>
            <NuxtLink
              v-if="item.href"
              :to="item.href"
              class="font-semibold text-fuchsia-700 hover:text-fuchsia-900"
              :class="compact ? 'inline-flex min-h-11 items-center' : undefined"
              :aria-label="`Details öffnen: ${item.title}`"
            >
              Details öffnen
            </NuxtLink>
          </div>
        </div>
      </li>
    </DataListShell>
    <EmptyState
      v-else-if="!loading && !error"
      :compact="compact"
      message="Für diesen Datensatz sind noch keine Ereignisse mit belegtem Zeitpunkt vorhanden."
    />
    <div v-if="hasMore" class="flex justify-center">
      <button class="button" type="button" :disabled="loading" @click="load(false)">
        Mehr laden
      </button>
    </div>
  </section>
</template>
