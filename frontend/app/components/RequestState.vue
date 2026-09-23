<script setup lang="ts">
import InlineAlert from '~/components/InlineAlert.vue'
import { dateTime } from '~/utils/presentation'
import type { ApiFailure } from '#shared/errors'
defineProps<{
  loading: boolean
  error: ApiFailure | null
  hasData?: boolean
  lastSuccess?: string | null
}>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <InlineAlert v-if="error" tone="warning">
    <p class="font-semibold">
      {{
        error.status === 401
          ? 'Zugang erforderlich'
          : error.status === 403
            ? 'Zugriff gesperrt'
            : 'Abruf fehlgeschlagen'
      }}
    </p>
    <p class="mt-1">{{ error.message }}</p>
    <p v-if="error.status === 401" class="mt-2">
      Bitte melde dich über „Admin-Anmeldung“ an. Nach Ablauf einer Sitzung ist eine erneute
      Anmeldung erforderlich.
    </p>
    <p v-if="hasData" class="mt-2 font-semibold">
      Die angezeigten Daten sind veraltet.
      <template v-if="lastSuccess"
        >Letzter erfolgreicher Abruf: {{ dateTime(lastSuccess) }}.</template
      >
    </p>
    <button class="button mt-3" :disabled="loading" @click="$emit('retry')">
      Erneut versuchen
    </button>
  </InlineAlert>
  <p v-if="loading" role="status" class="text-sm text-slate-600">
    {{ hasData ? 'Daten werden aktualisiert …' : 'Daten werden geladen …' }}
  </p>
</template>
