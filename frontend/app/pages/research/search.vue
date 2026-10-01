<script setup lang="ts">
import { researchAnswerMode } from '~/utils/research-answer'
definePageMeta({ layout: 'research' })
useHead({ title: 'Recherche · Kulturbytes' })
const route = useRoute()
const answer = computed(() => researchAnswerMode(route.query))
</script>
<template>
  <div class="space-y-3">
    <div class="research-toggle" aria-label="Recherchemodus">
      <button
        :aria-pressed="answer"
        @click="navigateTo({ path: '/research/search', query: { mode: 'answer' } })"
      >
        Frage beantworten
      </button>
      <button :aria-pressed="!answer" @click="navigateTo('/research/search')">
        Treffer suchen
      </button>
    </div>
    <ResearchQuestion v-if="answer" />
    <ResearchSearch v-else />
  </div>
</template>
