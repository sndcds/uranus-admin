<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { activityTypes } from '~/utils/activity'
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
    class="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-100 md:h-20 md:w-20"
    :class="presentation.tone"
  >
    <img
      v-if="item.image_url && !failed"
      :src="item.image_url"
      alt=""
      width="80"
      height="80"
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
