<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
defineProps<{ data: EntityDetail; loading: boolean }>()
</script>

<template>
  <EntityHero :item="data.item" section="images">
    <template #leading><AppIcon name="image" :size="32" class="text-rose-700" /></template>
    <template #context><span /></template>
  </EntityHero>
  <RecordSection title="Bildinformationen" surface="panel">
    <div class="operations-grid items-start" data-record-info-grid>
      <ActivityThumbnail :item="data.item" record />
      <CompactFacts
        :items="[
          { label: 'Bildverknüpfungen', value: data.item.facts.image_links },
          { label: 'Ohne Verknüpfung', value: data.item.facts.orphan },
        ]"
      />
    </div>
  </RecordSection>
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
