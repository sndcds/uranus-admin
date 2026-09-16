<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { activityName, activityTypes } from '~/utils/activity'
import type { ActivityItem } from '~/utils/activity'
const props = defineProps<{ item: ActivityItem }>()
const failed = ref(false)
watch(
  () => props.item.image_url,
  () => {
    failed.value = false
  },
)
const presentation = computed(() => activityTypes[props.item.entity_type])
</script>

<template>
  <div
    class="flex aspect-video w-24 shrink-0 self-start items-center justify-center overflow-hidden rounded-xl border border-slate-100 md:w-32"
    :class="presentation.tone"
  >
    <img
      v-if="item.image_url && !failed"
      :src="item.image_url"
      :alt="activityName(item)"
      width="320"
      height="180"
      loading="lazy"
      decoding="async"
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <AppIcon v-else :name="presentation.icon" :size="28" />
  </div>
</template>
