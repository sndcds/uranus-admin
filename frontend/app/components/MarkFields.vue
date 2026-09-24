<script setup lang="ts">
import type { MarkCreate } from '#shared/contracts'
import { markReasons, markUrgencies } from '~/utils/marks'
const reasons = defineModel<MarkCreate['reasons']>('reasons', { required: true })
const reasonDetail = defineModel<string>('reasonDetail', { required: true })
const urgency = defineModel<MarkCreate['urgency']>('urgency', { required: true })
</script>

<template>
  <div class="grid min-w-0 gap-4 lg:grid-cols-2">
    <fieldset>
      <legend class="label">Grund der Markierung (mindestens eine Auswahl)</legend>
      <div class="grid sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
        <label
          v-for="(label, value) in markReasons"
          :key="value"
          class="flex min-h-11 min-w-0 items-center gap-2 text-sm"
        >
          <input v-model="reasons" type="checkbox" :value="value" class="shrink-0" />{{ label }}
        </label>
      </div>
    </fieldset>
    <div class="min-w-0 space-y-3">
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
      <slot />
    </div>
  </div>
</template>
