<script setup lang="ts">
import type { GeocodeRequestDetail } from '#shared/contracts'
import { recordDateTime } from '~/utils/presentation'
defineProps<{ suggestion: GeocodeRequestDetail }>()
</script>

<template>
  <RecordSection title="Technische Informationen" class="border-t border-slate-200 pt-4">
    <dl class="type-metadata grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <dt>Generation</dt>
        <dd>{{ suggestion.generation }}</dd>
      </div>
      <div>
        <dt>Prüfversuche</dt>
        <dd>{{ suggestion.attempt_count }}</dd>
      </div>
      <div>
        <dt>Letzte Prüfung</dt>
        <dd>
          <time
            v-if="suggestion.checked_at"
            :datetime="suggestion.checked_at"
            :title="suggestion.checked_at"
            >{{ recordDateTime(suggestion.checked_at) }}</time
          ><span v-else>Noch nicht geprüft</span>
        </dd>
      </div>
      <div>
        <dt>Request-ID</dt>
        <dd class="break-all font-mono">{{ suggestion.id }}</dd>
      </div>
    </dl>
  </RecordSection>
</template>
