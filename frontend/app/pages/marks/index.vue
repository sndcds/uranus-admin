<script setup lang="ts">
import { markCreateSchema, markEntityTypeSchema } from '#shared/contracts'
import type { MarkCreate, MarkPage } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { markReasons, markStatuses, markUrgencies } from '~/utils/marks'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<MarkPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const saving = ref(false)
const formError = ref('')
const showCreate = ref(false)
const reasons = ref<MarkCreate['reasons']>([])
const reasonDetail = ref('')
const urgency = ref<MarkCreate['urgency']>('normal')
const note = ref('')
const statusFilter = ref('active')
const urgencyFilter = ref('')
const reasonFilter = ref('')
const sort = ref('urgency')
const scope = computed(() => {
  const kind = markEntityTypeSchema.safeParse(route.query.entity_type)
  const key = route.query.entity_key
  return kind.success && typeof key === 'string' && key.length > 0 && key.length <= 1024
    ? { entity_type: kind.data, entity_key: key }
    : null
})
let requestId = 0
let dataQuery = ''
async function load() {
  const id = ++requestId
  loading.value = true
  const queryKey = JSON.stringify(
    Object.entries(route.query).sort(([a], [b]) => a.localeCompare(b)),
  )
  if (queryKey !== dataQuery) {
    data.value = null
    showCreate.value = false
    formError.value = ''
  }
  error.value = null
  statusFilter.value = typeof route.query.status === 'string' ? route.query.status : 'active'
  urgencyFilter.value = typeof route.query.urgency === 'string' ? route.query.urgency : ''
  reasonFilter.value = typeof route.query.reason === 'string' ? route.query.reason : ''
  sort.value = typeof route.query.sort === 'string' ? route.query.sort : 'urgency'
  try {
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      query[key] = value
    }
    const result = await $adminApi.marks(query)
    if (id === requestId) {
      data.value = result
      dataQuery = queryKey
    }
  } catch (cause) {
    if (id === requestId) {
      error.value = asFailure(cause)
      if ([401, 403].includes(error.value.status)) data.value = null
    }
  } finally {
    if (id === requestId) loading.value = false
  }
}
function apply() {
  void router.push({
    query: {
      ...route.query,
      status: statusFilter.value,
      urgency: urgencyFilter.value || undefined,
      reason: reasonFilter.value || undefined,
      sort: sort.value,
      page: '1',
    },
  })
}
async function create() {
  if (!scope.value || saving.value) return
  const parsed = markCreateSchema.safeParse({
    ...scope.value,
    reasons: reasons.value,
    reason_detail: reasonDetail.value.trim() || null,
    urgency: urgency.value,
    note: note.value.trim() || null,
  })
  if (!parsed.success) {
    formError.value = 'Bitte wähle mindestens einen Grund und erläutere „Sonstiges“.'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    const result = await $adminApi.createMark(parsed.data)
    await router.push(`/marks/${result.id}`)
  } catch (cause) {
    formError.value = asFailure(cause).message
  } finally {
    saving.value = false
  }
}
onMounted(load)
watch(() => route.query, load)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <PageHeader title="Markierungen" description="Manuell markierte Datensätze und Notizen.">
      <button class="button" :disabled="loading" @click="load">
        <AppIcon name="refresh" :size="16" />Aktualisieren
      </button>
    </PageHeader>
    <RecordSection
      v-if="scope"
      :title="data?.items[0]?.entity_name ?? 'Markierungen zu diesem Datensatz'"
      surface="panel"
    >
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <EntityTypeBadge :type="scope.entity_type" /><code
          class="operations-meta [overflow-wrap:anywhere]"
          >{{ scope.entity_key }}</code
        >
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          class="button-primary"
          :aria-expanded="showCreate"
          aria-controls="mark-create"
          @click="showCreate = !showCreate"
        >
          Neue Markierung
        </button>
        <NuxtLink to="/marks" class="button">Alle markierten Datensätze</NuxtLink>
      </div>
      <form
        v-if="showCreate"
        id="mark-create"
        class="border-t border-slate-200 pt-4"
        @submit.prevent="create"
      >
        <fieldset :disabled="saving" class="space-y-4">
          <legend class="mb-3 font-bold">Markierung anlegen</legend>
          <MarkFields
            v-model:reasons="reasons"
            v-model:reason-detail="reasonDetail"
            v-model:urgency="urgency"
          >
            <label class="block"
              ><span class="label">Notiz (optional)</span
              ><textarea v-model="note" class="input w-full" maxlength="4000" />
            </label>
          </MarkFields>
          <button class="button-primary">
            {{ saving ? 'Speichert …' : 'Markierung speichern' }}
          </button>
        </fieldset>
        <InlineAlert v-if="formError" tone="error" compact class="mt-3">{{
          formError
        }}</InlineAlert>
      </form>
    </RecordSection>
    <p v-else class="muted">
      Markierungen und Notizen legst du direkt über einen Datensatz in der Aktivität, einer
      Arbeitsliste oder einem Prüfhinweis an.
    </p>
    <FilterBar compact @apply="apply">
      <label
        ><span class="label">Status</span
        ><select v-model="statusFilter" class="input">
          <option value="active">Offen und in Bearbeitung</option>
          <option value="all">Alle einschließlich erledigter</option>
          <option v-for="(label, value) in markStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Dringlichkeit filtern</span
        ><select v-model="urgencyFilter" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in markUrgencies" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Grund filtern</span
        ><select v-model="reasonFilter" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in markReasons" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Sortierung</span
        ><select v-model="sort" class="input">
          <option value="urgency">Dringlichkeit zuerst</option>
          <option value="newest">Neueste zuerst</option>
        </select></label
      >
      <template #actions>
        <button class="button-primary">Anwenden</button
        ><button
          type="button"
          class="button"
          @click="router.push({ query: scope ? { ...scope } : {} })"
        >
          Filter zurücksetzen
        </button>
      </template>
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Markierungen"
        :description="
          (route.query.sort ?? 'urgency') === 'urgency'
            ? 'Dringlichkeit zuerst · aktueller Bestand'
            : 'Neueste zuerst · aktueller Bestand'
        "
      />
      <DataListShell
        v-if="data.items.length"
        as="ul"
        dense
        aria-label="Markierungen"
        :aria-busy="loading"
      >
        <li
          v-for="item in data.items"
          :key="item.id"
          class="data-row grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
        >
          <div class="min-w-0 py-1">
            <h3 class="type-row-title">{{ item.entity_name }}</h3>
            <div class="mt-1 flex flex-wrap gap-1">
              <EntityTypeBadge :type="item.entity_type" /><StatusBadge
                :label="markStatuses[item.status]"
              /><StatusBadge
                :label="markUrgencies[item.urgency]"
                :tone="
                  item.urgency === 'urgent'
                    ? 'error'
                    : item.urgency === 'high'
                      ? 'warning'
                      : 'neutral'
                "
              />
            </div>
          </div>
          <div class="min-w-0 py-1">
            <p class="operations-meta">Gründe</p>
            <p class="text-xs">
              {{ item.reasons.map((reason) => markReasons[reason]).join(' · ') }}
            </p>
            <p v-if="item.reason_detail" class="mt-1 whitespace-pre-wrap text-xs text-slate-600">
              {{ item.reason_detail }}
            </p>
          </div>
          <div class="min-w-0 py-1 text-xs text-slate-600">
            <p>
              Angelegt:
              <time :datetime="item.created_at" title="Europe/Berlin">{{
                dateTime(item.created_at)
              }}</time>
            </p>
            <p>Angelegt von: {{ item.created_by }}</p>
            <p v-if="item.completed_at">
              Erledigt am
              <time :datetime="item.completed_at" title="Europe/Berlin">{{
                dateTime(item.completed_at)
              }}</time>
              · von {{ item.completed_by }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-x-3 xl:flex-col xl:items-start">
            <NuxtLink
              :to="`/marks/${item.id}`"
              class="action-link text-xs"
              :aria-label="`Markierung öffnen: ${item.entity_name}`"
              >Markierung öffnen</NuxtLink
            >
            <NuxtLink v-if="item.action" :to="item.action.href" class="action-link text-xs"
              >Öffnen</NuxtLink
            >
          </div>
        </li>
      </DataListShell>
      <EmptyState
        v-else-if="!error"
        variant="compact"
        message="Keine Markierungen für diese Auswahl."
      >
        <button
          v-if="
            Object.keys(route.query).some((key) => !['entity_type', 'entity_key'].includes(key))
          "
          class="action-link"
          @click="router.push({ query: scope ? { ...scope } : {} })"
        >
          Filter zurücksetzen
        </button>
      </EmptyState>
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        :to="(page) => ({ query: { ...route.query, page } })"
      />
      <TechnicalInfoBar
        :items="[
          { label: 'Sichtbare Einträge', value: data.items.length },
          { label: 'Gesamtzahl', value: data.pagination.total },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
        ]"
      />
    </template>
  </section>
</template>
