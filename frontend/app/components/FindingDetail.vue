<script setup lang="ts">
import { dateTime } from '~/utils/presentation'
import type { Finding } from '#shared/contracts'
const finding = ref<Finding | null>(null)
const dialog = useTemplateRef<HTMLDialogElement>('detail')
let trigger: HTMLElement | null = null
function open(value: Finding) {
  trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  finding.value = value
  dialog.value?.showModal()
}
function close() {
  dialog.value?.close()
  trigger?.focus()
}
defineExpose({ open })
</script>

<template>
  <dialog
    ref="detail"
    aria-labelledby="finding-title"
    class="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-xl overflow-y-auto rounded-2xl border-0 bg-white p-6 shadow-soft backdrop:bg-slate-900/40"
    @cancel.prevent="close"
  >
    <template v-if="finding">
      <div class="flex items-start justify-between gap-4">
        <h2 id="finding-title" class="break-words text-xl font-bold">{{ finding.entity_name }}</h2>
        <button class="rounded-lg p-2" aria-label="Details schließen" @click="close">
          <AppIcon name="close" />
        </button>
      </div>
      <div class="mt-3"><SeverityBadge :severity="finding.severity" /></div>
      <p class="mt-4 text-sm text-slate-700">{{ finding.message }}</p>
      <dl class="mt-5 grid gap-4 text-sm">
        <div>
          <dt class="font-semibold">Organisation</dt>
          <dd>{{ finding.organization_name }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Adresse</dt>
          <dd>
            {{
              [
                finding.address.street,
                finding.address.house_number,
                finding.address.postal_code,
                finding.address.city,
                finding.address.country,
              ]
                .filter(Boolean)
                .join(' ') || 'Nicht verfügbar'
            }}
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Kommende Termine</dt>
          <dd>
            {{ finding.upcoming_event_date_count }} · davon
            {{ finding.upcoming_published_event_date_count }} veröffentlicht,
            {{ finding.soon_published_event_date_count }} bald
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Beobachtet</dt>
          <dd>{{ dateTime(finding.last_seen_at) }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Erstmals gefunden</dt>
          <dd>{{ dateTime(finding.first_seen_at) }} · Live-Befund ohne gespeicherte Historie</dd>
        </div>
        <div>
          <dt class="font-semibold">Status</dt>
          <dd>
            {{
              finding.status === 'open'
                ? 'Offen (Live-Befund)'
                : (finding.status ?? 'Nicht verfügbar')
            }}
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Regel / Feld</dt>
          <dd class="break-all">{{ finding.rule }} / {{ finding.field }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Objekt-ID</dt>
          <dd class="break-all text-xs">{{ finding.entity_key }}</dd>
        </div>
      </dl>
      <p class="mt-5 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
        Bearbeiten, als geprüft markieren und ignorieren sind noch nicht verfügbar.
      </p>
      <button class="button mt-4" @click="close">Schließen</button>
    </template>
  </dialog>
</template>
