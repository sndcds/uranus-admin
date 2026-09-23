<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
import { metric } from '~/utils/presentation'
defineProps<{ data: EntityDetail; loading: boolean }>()
</script>

<template>
  <EntityHero :item="data.item" section="images">
    <template #leading><AppIcon name="image" :size="32" class="text-rose-700" /></template>
    <template #context><span /></template>
  </EntityHero>
  <ActivityThumbnail :item="data.item" record />
  <RecordSection title="Bildinformationen">
    <dl class="grid gap-4 sm:grid-cols-2">
      <div>
        <dt class="type-metadata">Bildverknüpfungen</dt>
        <dd class="type-body mt-1 font-semibold">{{ metric(data.item.facts.image_links) }}</dd>
      </div>
      <div>
        <dt class="type-metadata">Ohne Verknüpfung</dt>
        <dd class="type-body mt-1">
          {{
            data.item.facts.orphan == null
              ? 'Nicht verfügbar'
              : data.item.facts.orphan
                ? 'Ja'
                : 'Nein'
          }}
        </dd>
      </div>
    </dl>
  </RecordSection>
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
