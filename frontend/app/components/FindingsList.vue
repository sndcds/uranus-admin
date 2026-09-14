<script setup lang="ts">
import { dateTime } from '~/utils/presentation'
import type { Finding } from '#shared/contracts'
defineProps<{ items: Finding[] }>()
const detail = useTemplateRef('detail')
</script>

<template>
  <div class="divide-y divide-slate-100">
    <article
      v-for="finding in items"
      :key="finding.id"
      class="grid min-w-0 gap-4 p-5 md:grid-cols-[auto_1fr_auto] md:items-center"
    >
      <span
        aria-hidden="true"
        class="mt-1 hidden h-3 w-3 rounded-full md:block"
        :class="
          finding.severity === 'error'
            ? 'bg-rose-500'
            : finding.severity === 'warning'
              ? 'bg-amber-400'
              : 'bg-sky-400'
        "
      />
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="break-words font-semibold">{{ finding.entity_name }}</h3>
          <SeverityBadge :severity="finding.severity" /><span
            class="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600"
            >{{ finding.entity_type === 'venue' ? 'Venue' : finding.entity_type }}</span
          >
        </div>
        <p class="mt-1 break-words text-sm text-slate-600">{{ finding.message }}</p>
        <p class="mt-2 text-xs text-slate-500">
          {{ finding.organization_name }} · beobachtet {{ dateTime(finding.last_seen_at) }}
        </p>
      </div>
      <button
        class="button"
        :aria-label="`Befund zu ${finding.entity_name} ansehen`"
        @click="detail?.open(finding)"
      >
        Ansehen <AppIcon name="arrow" :size="15" />
      </button>
    </article>
  </div>
  <FindingDetail ref="detail" />
</template>
