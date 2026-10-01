<script setup lang="ts">
import { researchAnswerMode } from '~/utils/research-answer'
definePageMeta({
  layout: 'research',
  middleware: (to) => {
    if (researchAnswerMode(to.query)) {
      return navigateTo(
        { path: '/research', query: to.query },
        { replace: true, redirectCode: 302 },
      )
    }
  },
})
useHead({ title: 'Suche · Kulturbytes' })
</script>
<template>
  <div class="space-y-3">
    <NuxtLink
      to="/research"
      class="inline-flex min-h-11 items-center gap-2 text-sm text-blue-700 hover:underline"
    >
      <AppIcon name="arrow" :size="16" class="rotate-180" />Recherchefrage stellen
    </NuxtLink>
    <ResearchSearch />
  </div>
</template>
