<script setup lang="ts">
import { adminTimeZone, dateTime } from '~/utils/presentation'
defineProps<{ value: string | null | undefined }>()
</script>
<template>
  <time v-if="value" :datetime="value" :title="adminTimeZone">{{ dateTime(value) }}</time>
  <span v-else>Nicht verfügbar</span>
</template>
