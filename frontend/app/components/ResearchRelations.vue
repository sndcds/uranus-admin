<script setup lang="ts">
import type { ResearchDetail, GraphNode } from '#shared/contracts'
import { researchRelations } from '~/utils/research-relations'
import { researchHref } from '~/utils/research'
const props = defineProps<{ detail: ResearchDetail }>()
const graph = computed(() => researchRelations(props.detail))
const mode = ref<'list' | 'graph'>('list')
const selected = ref('')
const selectedNode = computed(() => graph.value.nodes.find((n) => n.id === selected.value))
function href(node: GraphNode) {
  return ['event', 'venue', 'organization'].includes(node.type)
    ? researchHref(node.type as 'event' | 'venue' | 'organization', node.key)
    : null
}
</script>
<template>
  <RecordSection
    title="Beziehungen"
    surface="panel"
    description="Belegte Verbindungen der sichtbaren Termin- oder Veranstaltungsseite. Weitere Verbindungen sind über die Seitennavigation erreichbar."
  >
    <template #actions
      ><button class="button" :aria-pressed="mode === 'list'" @click="mode = 'list'">Liste</button
      ><button class="button" :aria-pressed="mode === 'graph'" @click="mode = 'graph'">
        Graph
      </button></template
    >
    <EmptyState
      v-if="!graph.relations.length"
      message="Keine Beziehungen für diese Auswahl vorhanden."
      compact
    />
    <ul v-else-if="mode === 'list'" class="divide-y divide-slate-100">
      <li
        v-for="relation in graph.relations"
        :key="relation.id"
        class="flex flex-wrap items-center gap-2 py-2 text-sm"
      >
        <NuxtLink
          v-if="href(relation.sourceNode)"
          :to="href(relation.sourceNode)!"
          class="action-link"
          >{{ relation.sourceNode.label }}</NuxtLink
        ><span v-else>{{ relation.sourceNode.label }}</span
        ><span class="text-slate-500">{{ relation.label }} →</span
        ><NuxtLink
          v-if="href(relation.targetNode)"
          :to="href(relation.targetNode)!"
          class="action-link"
          >{{ relation.targetNode.label }}</NuxtLink
        ><span v-else>{{ relation.targetNode.label }}</span>
      </li>
    </ul>
    <template v-else
      ><ClientOnly
        ><EntityGraph
          :nodes="graph.nodes"
          :edges="graph.edges"
          :root="graph.root"
          :selected="selected"
          :depth="2"
          show-labels
          @select="selected = $event"
      /></ClientOnly>
      <p v-if="graph.truncated" class="type-metadata">
        Der Graph zeigt maximal 100 Knoten und 200 Verbindungen.
      </p>
      <p v-if="selectedNode" class="type-body">
        {{ selectedNode.label }}
        <NuxtLink v-if="href(selectedNode)" :to="href(selectedNode)!" class="action-link"
          >Dossier öffnen →</NuxtLink
        >
      </p></template
    >
  </RecordSection>
</template>
