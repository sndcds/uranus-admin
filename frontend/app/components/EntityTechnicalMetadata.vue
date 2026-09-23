<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import { adminTimeZone, recordDateTime } from '~/utils/presentation'
const props = defineProps<{ data: EntityDetail }>()
const feedback = ref('')
let revision = 0
watch(
  () => props.data.item.entity_key,
  () => {
    revision++
    feedback.value = ''
  },
)
onBeforeUnmount(() => {
  revision++
})
async function copy() {
  const current = revision
  try {
    await navigator.clipboard.writeText(props.data.item.entity_key)
    if (revision === current) feedback.value = 'UUID kopiert.'
  } catch {
    if (revision === current)
      feedback.value = 'Kopieren nicht verfügbar. Die UUID kann als Text ausgewählt werden.'
  }
}
</script>

<template>
  <RecordSection title="Technische Informationen">
    <dl class="space-y-3 border-t border-slate-200 pt-4">
      <div>
        <dt class="type-metadata">UUID</dt>
        <dd class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <code class="type-metadata break-all">{{ data.item.entity_key }}</code>
          <button type="button" class="action-link" @click="copy">
            <AppIcon name="copy" :size="14" />UUID kopieren
          </button>
        </dd>
      </div>
      <div v-if="data.item.created_at">
        <dt class="type-metadata">Quelldatensatz angelegt</dt>
        <dd class="type-metadata">
          <time :datetime="data.item.created_at" :title="adminTimeZone">{{
            recordDateTime(data.item.created_at)
          }}</time>
        </dd>
      </div>
      <div>
        <dt class="type-metadata">Datenstand des Abrufs</dt>
        <dd class="type-metadata">
          <time :datetime="data.observed_at">{{ recordDateTime(data.observed_at) }}</time> ·
          {{ adminTimeZone }}
        </dd>
      </div>
    </dl>
    <p role="status" class="type-metadata">{{ feedback }}</p>
  </RecordSection>
</template>
