<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppModal from './AppModal.vue'
import { activityImagePreviewUrl, activityName, activityTypes } from '~/utils/activity'
import type { ActivityItem } from '~/utils/activity'
const props = defineProps<{ item: ActivityItem }>()
const failed = ref(false)
const previewFailed = ref(false)
const modal = ref<InstanceType<typeof AppModal> | null>(null)
watch(
  () => props.item.image_url,
  () => {
    failed.value = false
    modal.value?.close()
  },
)
const presentation = computed(() => activityTypes[props.item.entity_type])
const name = computed(() => activityName(props.item))
const previewUrl = computed(() => activityImagePreviewUrl(props.item.image_url))
function openPreview() {
  previewFailed.value = false
  void modal.value?.open()
}
</script>

<template>
  <div class="w-24 shrink-0 self-start md:w-32">
    <button
      v-if="item.image_url && !failed"
      type="button"
      class="block w-full overflow-hidden rounded-xl border border-slate-100 transition-shadow hover:ring-2 hover:ring-fuchsia-300"
      :aria-label="`Bild vergrößern: ${name}`"
      aria-haspopup="dialog"
      @click="openPreview"
    >
      <img
        :src="item.image_url"
        :alt="name"
        loading="lazy"
        decoding="async"
        crossorigin="anonymous"
        referrerpolicy="no-referrer"
        class="block h-auto w-full"
        @error="failed = true"
      />
    </button>
    <div
      v-else
      class="flex h-16 items-center justify-center rounded-xl border border-slate-100 md:h-20"
      :class="presentation.tone"
    >
      <AppIcon :name="presentation.icon" :size="28" />
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
