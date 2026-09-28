<script setup lang="ts">
defineProps<{ modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | undefined] }>()
</script>
<template>
  <AdministrativeAreaSelect
    :model-value="modelValue"
    workspace="research"
    dossier-link
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
