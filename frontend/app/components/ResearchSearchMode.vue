<script setup lang="ts">
defineProps<{ disabled?: boolean }>()
const mode = defineModel<'classic' | 'semantic'>({ default: 'classic' })
const id = useId()
</script>
<template>
  <fieldset :disabled="disabled" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
    <legend class="sr-only">Suchmodus</legend>
    <label class="inline-flex min-h-11 items-center gap-2">
      <input v-model="mode" type="radio" :name="id" value="classic" />Klassische Suche
    </label>
    <label class="inline-flex min-h-11 items-center gap-2">
      <input v-model="mode" type="radio" :name="id" value="semantic" />Semantisch · Experimentell
    </label>
  </fieldset>
  <p v-if="mode === 'semantic'" class="text-sm text-slate-600">
    Findet Veranstaltungen auch dann, wenn deine Begriffe nicht wörtlich im Text vorkommen.
  </p>
</template>
