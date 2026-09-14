<script setup lang="ts">
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
  <div
    v-if="error"
    class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"
    role="alert"
  >
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
      Eine reguläre Admin-Anmeldung wird vom Backend noch nicht angeboten. Ohne gültigen Zugang
      bleiben die Verwaltungsdaten gesperrt.
    </p>
    <p v-if="hasData" class="mt-2 font-semibold">
      Die angezeigten Daten sind veraltet. Letzter erfolgreicher Abruf: {{ dateTime(lastSuccess) }}.
    </p>
    <button class="button mt-3" :disabled="loading" @click="$emit('retry')">
      Erneut versuchen
    </button>
  </div>
  <p v-if="loading" role="status" class="text-sm text-slate-600">
    {{ hasData ? 'Daten werden aktualisiert …' : 'Daten werden geladen …' }}
  </p>
</template>
