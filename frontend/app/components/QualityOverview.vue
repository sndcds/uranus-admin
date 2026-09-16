<script setup lang="ts">
import { metric } from '~/utils/presentation'
import type { DashboardSummary } from '#shared/contracts'
defineProps<{ data: DashboardSummary | null }>()
</script>

<template>
  <section class="card p-5">
    <h2 class="font-bold">Datenqualität</h2>
    <p class="mt-2 muted">
      {{ metric(data?.quality.total) }}
      {{
        data?.quality.mode === 'live'
          ? 'Befunde aus der Live-Diagnose.'
          : 'gespeicherte, noch nicht erledigte Befunde.'
      }}
    </p>
    <dl class="my-4 flex flex-wrap gap-4 text-sm">
      <div>
        <dt>Fehler</dt>
        <dd>{{ metric(data?.quality.errors) }}</dd>
      </div>
      <div>
        <dt>Warnungen</dt>
        <dd>{{ metric(data?.quality.warnings) }}</dd>
      </div>
      <div>
        <dt>Hinweise</dt>
        <dd>{{ metric(data?.quality.info) }}</dd>
      </div>
    </dl>
    <ul
      v-if="data?.quality.rules"
      class="divide-y divide-slate-100 border-y border-slate-100 text-sm"
    >
      <li v-for="rule in data.quality.rules" :key="rule" class="break-words py-3">
        <NuxtLink
          :to="{ path: '/findings', query: { rule, mode: data.quality.mode } }"
          class="text-fuchsia-700 hover:underline"
          >{{ rule }}</NuxtLink
        >
      </li>
    </ul>
    <NuxtLink to="/findings" class="button mt-5 w-full">Qualitätsbefunde öffnen</NuxtLink>
  </section>
</template>
