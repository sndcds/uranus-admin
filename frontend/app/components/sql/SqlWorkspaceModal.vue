<script setup lang="ts">
import { ref } from 'vue'
import AppModal from '../AppModal.vue'
import SqlWorkspace from './SqlWorkspace.vue'
defineProps<{ title: string; subtitle: string; closeLabel?: string; busy?: boolean }>()
const emit = defineEmits<{ close: []; cancel: [] }>()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
defineExpose({ open: () => modal.value?.open(), close: () => modal.value?.close() })
</script>
<template>
  <AppModal
    ref="modal"
    :title="title"
    :subtitle="subtitle"
    :close-label="closeLabel"
    wide
    workspace
    :close-blocked="busy"
    @close-blocked="emit('cancel')"
    @close="emit('close')"
  >
    <template #icon
      ><span
        class="flex size-11 shrink-0 items-center justify-center rounded-full bg-fuchsia-100 text-fuchsia-700"
        ><AppIcon name="database" :size="25" /></span
    ></template>
    <template #actions><slot name="actions" /></template>
    <SqlWorkspace>
      <template #context><slot name="context" /></template>
      <template #navigation><slot name="navigation" /></template>
      <slot />
    </SqlWorkspace>
  </AppModal>
</template>
