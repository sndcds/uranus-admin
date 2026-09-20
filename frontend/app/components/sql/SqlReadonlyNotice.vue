<template>
  <div
    class="flex gap-3 rounded-lg border border-blue-100 bg-blue-50/60 p-3 text-xs text-slate-600"
  >
    <AppIcon name="info" class="mt-0.5 text-blue-600" :size="16" />
    <div>
      <p class="mb-1 font-semibold text-blue-900">Hinweis · READ ONLY</p>
      <p>
        Diese registrierte Abfrage ist schreibgeschützt. Änderungen an Daten sind nicht möglich.
      </p>
    </div>
  </div>
</template>
