<script setup lang="ts">
defineProps<{ columns: string[]; rows: Record<string, string | number | boolean | null>[] }>()
</script>
<template>
  <div>
    <h3 class="font-semibold">Quelldaten</h3>
    <p v-if="!rows.length">Keine Ergebniszeilen.</p>
    <div v-else class="overflow-auto">
      <table class="w-full text-left text-xs">
        <caption class="sr-only">
          Diagnose-Ergebnis
        </caption>
        <thead>
          <tr>
            <th v-for="column in columns" :key="column" scope="col" class="p-2">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="index">
            <td v-for="column in columns" :key="column" class="max-w-80 break-words p-2 align-top">
              {{ row[column] === null ? 'NULL' : row[column] }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
