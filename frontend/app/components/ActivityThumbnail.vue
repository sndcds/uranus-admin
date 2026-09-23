<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppModal from './AppModal.vue'
import { activityImagePreviewUrl, activityName, activityTypes } from '~/utils/activity'
import type { ActivityItem } from '~/utils/activity'
const props = defineProps<{ item: ActivityItem; record?: boolean }>()
const failed = ref(false)
const previewFailed = ref(false)
const modal = ref<InstanceType<typeof AppModal> | null>(null)
watch([() => props.item.entity_key, () => props.item.image_url], () => {
  failed.value = false
  modal.value?.close()
})
const presentation = computed(() => activityTypes[props.item.entity_type])
const name = computed(() => activityName(props.item))
const previewUrl = computed(() => activityImagePreviewUrl(props.item.image_url))
const source = computed(() => (props.record ? previewUrl.value : props.item.image_url))
function openPreview() {
  previewFailed.value = false
  void modal.value?.open()
}
</script>

<template>
  <div
    :class="record ? 'w-full min-w-0' : 'w-24 shrink-0 self-start md:w-32'"
    :data-record-preview="record ? '' : undefined"
  >
    <button
      v-if="source && !failed"
      type="button"
      class="block w-full overflow-hidden rounded-xl border border-slate-100 transition-shadow hover:ring-2 hover:ring-fuchsia-300"
      :class="
        record
          ? 'flex h-[min(55dvh,32rem)] items-center justify-center bg-slate-50 p-3'
          : ['organization', 'venue'].includes(item.entity_type)
            ? 'bg-white p-3'
            : ''
      "
      :aria-label="`Bild vergrößern: ${name}`"
      aria-haspopup="dialog"
      @click="openPreview"
    >
      <img
        :src="source"
        :alt="name"
        loading="lazy"
        decoding="async"
        crossorigin="anonymous"
        referrerpolicy="no-referrer"
        :class="
          record
            ? 'block h-auto w-auto max-h-full max-w-full object-contain'
            : 'block h-auto w-full'
        "
        @error="failed = true"
      />
    </button>
    <div
      v-else
      class="flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-100 p-3"
      :class="[presentation.tone, record ? 'h-[min(55dvh,32rem)]' : 'h-16 md:h-20']"
    >
      <AppIcon :name="presentation.icon" :size="28" />
      <p v-if="record" role="status" class="type-body text-center">
        {{ failed ? 'Bildvorschau konnte nicht geladen werden.' : 'Keine Bildvorschau verfügbar.' }}
      </p>
    </div>
  </div>
  <AppModal ref="modal" :title="name" close-label="Bildansicht schließen" wide>
    <p v-if="previewFailed" role="alert" class="mt-4 text-sm text-slate-600">
      Das Bild konnte nicht geladen werden. Bitte die Bildansicht erneut öffnen.
    </p>
    <img
      v-else-if="previewUrl"
      :src="previewUrl"
      :alt="name"
      decoding="async"
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
      class="mx-auto mt-4 block h-auto max-h-[70dvh] w-auto max-w-full object-contain"
      @error="previewFailed = true"
    />
  </AppModal>
</template>
