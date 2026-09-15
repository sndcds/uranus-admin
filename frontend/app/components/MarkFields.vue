<script setup lang="ts">
import type { MarkCreate } from '#shared/contracts'
import { markReasons, markUrgencies } from '~/utils/marks'
const reasons = defineModel<MarkCreate['reasons']>('reasons', { required: true })
const reasonDetail = defineModel<string>('reasonDetail', { required: true })
const urgency = defineModel<MarkCreate['urgency']>('urgency', { required: true })
</script>

<template>
  <fieldset>
    <legend class="label">Grund der Markierung (mindestens eine Auswahl)</legend>
    <div class="grid gap-2 sm:grid-cols-2">
      <label v-for="(label, value) in markReasons" :key="value" class="flex items-start gap-2">
        <input v-model="reasons" type="checkbox" :value="value" class="mt-1" />{{ label }}
      </label>
    </div>
  </fieldset>
  <label class="block"
    ><span class="label"
      >Erläuterung zum Grund{{
        reasons.includes('other') ? ' (erforderlich)' : ' (optional)'
      }}</span
    >
    <textarea
      v-model="reasonDetail"
      class="input w-full"
      maxlength="2000"
      :required="reasons.includes('other')"
    />
  </label>
  <label class="block"
    ><span class="label">Dringlichkeit</span>
    <select v-model="urgency" class="input">
      <option v-for="(label, value) in markUrgencies" :key="value" :value="value">
        {{ label }}
      </option>
    </select>
  </label>
</template>
