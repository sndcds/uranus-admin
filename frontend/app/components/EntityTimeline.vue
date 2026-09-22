<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TimelineEntityType, TimelineItem } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { adminTimeZone, dateTime } from '~/utils/presentation'

const props = defineProps<{ entityType: TimelineEntityType; entityKey: string }>()
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
  <section class="space-y-3" aria-labelledby="entity-timeline-heading">
    <SectionHeader
      title-id="entity-timeline-heading"
      title="Verlauf"
      description="Belegte Quell- und Admin-Ereignisse, neueste zuerst."
    />
    <RequestState
      :loading="loading"
      :error="error"
      :has-data="items.length > 0"
      @retry="load(items.length === 0)"
    />
    <DataListShell v-if="items.length" as="ul" aria-label="Datensatzverlauf">
      <li v-for="item in items" :key="item.id" class="data-row flex gap-3">
        <span
          class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
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
          <p v-if="item.summary" class="mt-1 whitespace-pre-line text-sm text-slate-700">
            {{ item.summary }}
          </p>
          <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <SeverityBadge v-if="item.metadata.severity" :severity="item.metadata.severity" />
            <span v-if="item.actor">{{ item.actor }}</span>
            <NuxtLink
              v-if="item.href"
              :to="item.href"
              class="font-semibold text-fuchsia-700 hover:text-fuchsia-900"
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
      message="Für diesen Datensatz sind noch keine Ereignisse mit belegtem Zeitpunkt vorhanden."
    />
    <div v-if="hasMore" class="flex justify-center">
      <button class="button" type="button" :disabled="loading" @click="load(false)">
        Mehr laden
      </button>
    </div>
  </section>
</template>
