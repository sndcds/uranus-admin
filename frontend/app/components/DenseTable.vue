<script setup lang="ts" generic="T extends Record<string, unknown>">
import { useId } from 'vue'
import { operationValue } from '~/utils/operations'
import EmptyState from './EmptyState.vue'
withDefaults(
  defineProps<{
    caption: string
    columns: readonly { key: keyof T & string; label: string; rowHeader?: boolean }[]
    rows: readonly T[]
    rowKey: (row: T) => string | number
    mobile?: 'stack' | 'scroll'
    emptyMessage?: string
    busy?: boolean
  }>(),
  { mobile: 'stack', emptyMessage: 'Keine Ergebnisse für diese Auswahl.' },
)
const id = useId()
</script>

<template>
  <div class="section-table" :aria-busy="busy">
    <div
      :class="mobile === 'scroll' ? 'overflow-x-auto rounded-xl' : 'rounded-xl'"
      :tabindex="mobile === 'scroll' ? 0 : undefined"
      :role="mobile === 'scroll' ? 'region' : undefined"
      :aria-label="mobile === 'scroll' ? caption : undefined"
    >
      <table
        class="operations-table"
        :class="mobile === 'stack' ? 'operations-table-stack' : 'min-w-[40rem]'"
        role="table"
      >
        <caption class="sr-only">
          {{
            caption
          }}
        </caption>
        <thead role="rowgroup">
          <tr role="row">
            <th
              v-for="column in columns"
              :id="`${id}-${column.key}`"
              :key="column.key"
              scope="col"
              role="columnheader"
            >
              {{ column.label }}
            </th>
            <th v-if="$slots.actions" :id="`${id}-actions`" scope="col" role="columnheader">
              Aktionen
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          <tr v-for="row in rows" :key="rowKey(row)" role="row">
            <component
              :is="column.rowHeader ? 'th' : 'td'"
              v-for="column in columns"
              :key="column.key"
              :scope="column.rowHeader ? 'row' : undefined"
              :role="column.rowHeader ? 'rowheader' : 'cell'"
              :headers="`${id}-${column.key}`"
            >
              <span v-if="mobile === 'stack'" class="operations-cell-label" aria-hidden="true">{{
                column.label
              }}</span>
              <div class="min-w-0">
                <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">{{
                  operationValue(row[column.key])
                }}</slot>
              </div>
            </component>
            <td v-if="$slots.actions" role="cell" :headers="`${id}-actions`">
              <span v-if="mobile === 'stack'" class="operations-cell-label" aria-hidden="true"
                >Aktionen</span
              >
              <div class="flex min-w-0 flex-wrap items-center gap-2">
                <slot name="actions" :row="row" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-if="!rows.length && !busy" :message="emptyMessage" compact class="m-3" />
    <p v-if="busy" role="status" class="operations-meta p-3">Daten werden aktualisiert …</p>
  </div>
</template>
