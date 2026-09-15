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
async function load() {
  const id = ++requestId
  loading.value = true
  data.value = null
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
    if (id === requestId) data.value = result
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
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
watch(
  useState('admin-access-revision', () => 0),
  () => {
    showCreate.value = false
    reasons.value = []
    reasonDetail.value = note.value = ''
    void load()
  },
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <h2 class="text-2xl font-bold">Markierungen</h2>
    <div v-if="scope" class="card space-y-3 break-words p-5">
      <p class="font-semibold">
        {{ data?.items[0]?.entity_name ?? 'Markierungen zu diesem Datensatz' }}
      </p>
      <p class="muted">{{ scope.entity_type }} · {{ scope.entity_key }}</p>
      <div class="flex flex-wrap gap-3">
        <button
          class="button-primary"
          :aria-expanded="showCreate"
          @click="showCreate = !showCreate"
        >
          Neue Markierung
        </button>
        <NuxtLink to="/marks" class="button">Alle markierten Datensätze</NuxtLink>
      </div>
      <form v-if="showCreate" class="border-t border-slate-200 pt-4" @submit.prevent="create">
        <fieldset :disabled="saving" class="space-y-4">
          <legend class="mb-3 font-bold">Markierung anlegen</legend>
          <MarkFields
            v-model:reasons="reasons"
            v-model:reason-detail="reasonDetail"
            v-model:urgency="urgency"
          />
          <label class="block"
            ><span class="label">Notiz (optional)</span
            ><textarea v-model="note" class="input w-full" maxlength="4000" />
          </label>
          <button class="button-primary">
            {{ saving ? 'Speichert …' : 'Markierung speichern' }}
          </button>
        </fieldset>
        <p v-if="formError" role="alert" class="mt-3 text-red-700">{{ formError }}</p>
      </form>
    </div>
    <p v-else class="muted">
      Markierungen und Notizen legst du direkt über einen Datensatz in der Aktivität, einer
      Arbeitsliste oder einem Prüfhinweis an.
    </p>
    <form class="card flex flex-wrap items-end gap-3 p-5" @submit.prevent="apply">
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
      <button class="button-primary">Anwenden</button>
    </form>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <p class="muted">{{ data.pagination.total }} Markierungen</p>
      <article v-for="item in data.items" :key="item.id" class="card space-y-2 break-words p-5">
        <h3 class="font-bold">
          <NuxtLink :to="`/marks/${item.id}`" class="text-fuchsia-700">{{
            item.entity_name
          }}</NuxtLink>
        </h3>
        <div class="flex flex-wrap gap-2">
          <span class="rounded-full bg-slate-100 px-3 py-1 text-sm">{{
            markStatuses[item.status]
          }}</span>
          <span
            class="rounded-full px-3 py-1 text-sm font-semibold"
            :class="
              item.urgency === 'urgent'
                ? 'bg-red-100 text-red-800'
                : item.urgency === 'high'
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-slate-100 text-slate-700'
            "
            >{{ markUrgencies[item.urgency] }}</span
          >
        </div>
        <p>{{ item.reasons.map((reason) => markReasons[reason]).join(' · ') }}</p>
        <p v-if="item.reason_detail" class="whitespace-pre-wrap">{{ item.reason_detail }}</p>
        <p class="muted">Angelegt: {{ dateTime(item.created_at) }} · {{ item.created_by }}</p>
        <p v-if="item.completed_at">
          Erledigt am {{ dateTime(item.completed_at) }} · von {{ item.completed_by }}
        </p>
        <NuxtLink :to="`/marks/${item.id}`" class="button">Notizen &amp; Verlauf öffnen</NuxtLink>
      </article>
      <p v-if="!data.items.length">Keine Markierungen für diese Auswahl.</p>
      <div class="flex gap-3">
        <NuxtLink
          v-if="data.pagination.page > 1"
          class="button"
          :to="{ query: { ...route.query, page: data.pagination.page - 1 } }"
          >Zurück</NuxtLink
        >
        <NuxtLink
          v-if="data.pagination.page < data.pagination.pages"
          class="button"
          :to="{ query: { ...route.query, page: data.pagination.page + 1 } }"
          >Weiter</NuxtLink
        >
      </div>
    </template>
  </section>
</template>
