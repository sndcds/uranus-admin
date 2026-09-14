<script setup lang="ts">
import { metric } from '~/utils/presentation'
import type { DashboardSummary } from '#shared/contracts'
defineProps<{ data: DashboardSummary | null }>()
</script>

<template>
  <section class="card p-5">
    <h2 class="font-bold">Datenqualität</h2>
    <p class="mt-2 muted">
      {{ metric(data?.quality.total) }} Befunde aus den geprüften Quelltabellen.
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
    <ul v-if="data?.quality.rules" class="space-y-2 break-words text-sm">
      <li v-for="rule in data.quality.rules" :key="rule">
        <NuxtLink
          :to="{ path: '/findings', query: { rule } }"
          class="text-fuchsia-700 hover:underline"
          >{{ rule }}</NuxtLink
        >
      </li>
    </ul>
    <NuxtLink to="/findings" class="button mt-5 w-full">Qualitätsbefunde öffnen</NuxtLink>
  </section>
</template>
