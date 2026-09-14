<script setup lang="ts">
import { metric } from '~/utils/presentation'
import type { DashboardSummary } from '#shared/contracts'
defineProps<{ data: DashboardSummary | null }>()
</script>

<template>
  <section class="card p-5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="font-bold">Datenqualität</h2>
        <p class="mt-1 muted">Aktuell verfügbare Qualitätsregel</p>
      </div>
      <span class="rounded-xl bg-fuchsia-50 px-3 py-1.5 text-xs font-semibold text-fuchsia-700">{{
        data ? `${metric(data.quality.total)} Befunde` : 'Nicht verfügbar'
      }}</span>
    </div>
    <div class="mt-5 space-y-4">
      <div>
        <div class="mb-1.5 flex justify-between gap-3 text-sm">
          <NuxtLink
            to="/findings?rule=venue_missing_geolocation"
            class="font-medium hover:underline"
            >Venue ohne Geoposition</NuxtLink
          ><strong>{{ metric(data?.quality.total) }}</strong>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
          <div
            v-if="data && data.quality.total > 0"
            class="h-full w-full rounded-full bg-amber-400"
          />
        </div>
        <p class="mt-1 text-xs text-slate-500">
          {{
            data && data.quality.total > 0
              ? 'Alle derzeit geprüften Befunde stammen aus dieser Regel.'
              : 'Live-Auswertung beim Abruf.'
          }}
        </p>
      </div>
      <div
        v-for="rule in ['Ungültige URL', 'Event ohne Hauptbild', 'Offene Einladung']"
        :key="rule"
      >
        <div class="flex justify-between gap-3 text-sm text-slate-500">
          <span>{{ rule }}</span
          ><span class="text-xs">Noch nicht verfügbar</span>
        </div>
        <div class="mt-1.5 h-2 rounded-full bg-slate-100" />
      </div>
    </div>
    <NuxtLink to="/findings?rule=venue_missing_geolocation" class="button mt-5 w-full"
      >Qualitätsbefunde öffnen</NuxtLink
    >
  </section>
</template>
