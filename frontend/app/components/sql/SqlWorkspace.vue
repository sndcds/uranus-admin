<script setup lang="ts">
import SqlReadonlyNotice from './SqlReadonlyNotice.vue'
defineProps<{ page?: boolean }>()
</script>
<template>
  <div
    class="sql-workspace grid min-w-0 text-sm"
    :class="
      page
        ? 'sql-operations-workspace'
        : 'md:max-h-[calc(100dvh-7rem)] md:grid-cols-[260px_minmax(0,1fr)]'
    "
  >
    <aside
      class="min-h-0 min-w-0 border-b border-slate-200 bg-slate-50/70 p-4"
      :class="
        page
          ? 'operations-workspace-sidebar sql-context'
          : 'md:overflow-y-auto md:border-r md:border-b-0 md:row-start-1 md:col-start-1'
      "
      :aria-label="page ? 'Datenbankkontext' : undefined"
    >
      <slot name="context" />
      <nav v-if="$slots.navigation" class="mt-5 space-y-1" aria-label="SQL-Kontext">
        <slot name="navigation" />
      </nav>
    </aside>
    <component
      :is="page ? 'section' : 'main'"
      class="min-h-0 min-w-0 space-y-5 p-4"
      :class="
        page
          ? 'operations-workspace-main'
          : 'md:max-h-[calc(100dvh-7rem)] md:overflow-y-auto md:col-start-2 md:row-span-2'
      "
      :aria-label="page ? 'SQL-Arbeitsfläche' : undefined"
    >
      <slot />
    </component>
    <div
      v-if="!page"
      class="border-t border-slate-200 bg-slate-50/70 p-4 md:border-t-0 md:border-r md:col-start-1 md:row-start-2"
    >
      <SqlReadonlyNotice />
    </div>
  </div>
</template>
<style>
.sql-workspace {
  grid-template-rows: minmax(0, 1fr) auto;
}
.sql-workspace .sql-nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.65rem 0.75rem;
  border-radius: 0.5rem;
  color: #475569;
  text-align: left;
}
.sql-workspace .sql-nav[aria-current='page'] {
  background: #fae8ff;
  color: #a21caf;
  font-weight: 600;
}
.sql-workspace .admin-table {
  font-size: 0.75rem;
}
.sql-workspace .admin-table :is(td, th) {
  padding: 0.4rem 0.65rem;
  border-right: 1px solid #f1f5f9;
}
.sql-workspace .button,
.sql-workspace .button-primary {
  padding: 0.5rem 0.65rem;
  font-size: 0.7rem;
}
.sql-operations-workspace {
  grid-template-rows: auto;
}
.sql-operations-workspace .sql-context {
  border-radius: 0.75rem 0.75rem 0 0;
}
@media (min-width: 1280px) {
  .sql-operations-workspace {
    grid-template-columns: 11rem minmax(0, 1fr);
  }
  .sql-operations-workspace .sql-context {
    border-bottom: 0;
    border-right: 1px solid #e2e8f0;
    border-radius: 0.75rem 0 0 0;
  }
}
</style>
