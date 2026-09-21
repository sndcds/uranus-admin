<script setup lang="ts">
import SqlReadonlyNotice from './SqlReadonlyNotice.vue'
</script>
<template>
  <div
    class="sql-workspace grid min-w-0 text-sm md:max-h-[calc(100dvh-7rem)] md:grid-cols-[260px_minmax(0,1fr)]"
  >
    <aside
      class="min-h-0 min-w-0 md:overflow-y-auto border-b border-slate-200 bg-slate-50/70 p-4 md:border-r md:border-b-0 md:row-start-1 md:col-start-1"
    >
      <slot name="context" />
      <nav class="mt-5 space-y-1" aria-label="SQL-Kontext"><slot name="navigation" /></nav>
    </aside>
    <main
      class="min-h-0 min-w-0 space-y-5 p-4 md:max-h-[calc(100dvh-7rem)] md:overflow-y-auto md:col-start-2 md:row-span-2"
    >
      <slot />
    </main>
    <div
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
</style>
