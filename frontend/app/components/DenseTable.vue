<script setup lang="ts" generic="T extends Record<string, unknown>">
import { useId } from 'vue'
import { operationValue } from '~/utils/operations'
import EmptyState from './EmptyState.vue'
withDefaults(
  defineProps<{
    caption: string
    columns: readonly {
      key: keyof T & string
      label: string
      rowHeader?: boolean
      width?: string
    }[]
    rows: readonly T[]
    rowKey: (row: T) => string | number
    mobile?: 'stack' | 'scroll'
    stackAt?: 'mobile' | 'tablet'
    emptyMessage?: string
    busy?: boolean
  }>(),
  { mobile: 'stack', stackAt: 'mobile', emptyMessage: 'Keine Ergebnisse für diese Auswahl.' },
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
        :class="
          mobile === 'stack'
            ? ['operations-table-stack', { 'operations-table-tablet': stackAt === 'tablet' }]
            : 'min-w-[40rem]'
        "
        role="table"
      >
        <caption class="sr-only">
          {{
            caption
          }}
        </caption>
        <colgroup>
          <col
            v-for="column in columns"
            :key="column.key"
            :style="column.width ? { width: column.width } : undefined"
          />
          <col v-if="$slots.actions" />
        </colgroup>
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

<style scoped>
/* Opt-in for operational lists: preserve the existing mobile-only default. */
@media (max-width: 1100px) {
  .operations-table-tablet,
  .operations-table-tablet tbody {
    display: block;
    width: 100%;
  }
  .operations-table-tablet colgroup {
    display: none;
  }
  .operations-table-tablet thead {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
  .operations-table-tablet tbody tr {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    height: auto;
    padding: 8px 0;
    border-bottom: 1px solid #e2e8f0;
  }
  .operations-table-tablet tbody tr:last-child {
    border-bottom: 0;
  }
  .operations-table-tablet tbody :is(th, td) {
    display: block;
    min-width: 0;
    border: 0;
  }
  .operations-table-tablet .operations-cell-label {
    display: block;
    font-size: 12px;
    font-weight: 400;
    color: #475569;
  }
}
@media (max-width: 639px) {
  .operations-table-tablet tbody tr {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
