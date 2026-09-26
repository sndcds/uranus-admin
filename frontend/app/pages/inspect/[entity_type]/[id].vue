<script setup lang="ts">
import type { ActivityPage, EntityDetail, QueuePage } from '#shared/contracts'
import { inspectorIdentity, inspectorSection } from '~/utils/inspector'
import { entitySections } from '~/utils/entities'
import { entityPresentation } from '~/utils/activity'
import { dateTime } from '~/utils/presentation'
import { useOperationsRequest } from '~/composables/useOperationsRequest'

definePageMeta({
  key: (route) => route.path,
  validate: (route) =>
    !!inspectorIdentity(String(route.params.entity_type), String(route.params.id)),
})
const route = useRoute()
const { $adminApi } = useNuxtApp()
const type = String(route.params.entity_type)
const key = String(route.params.id)
const section = inspectorSection(type)
const timelineType = section ? entitySections[section].type : undefined
const record = useOperationsRequest<EntityDetail | ActivityPage>()
const queue = useOperationsRequest<QueuePage>()
const detail = computed(() =>
  record.data.value && 'item' in record.data.value ? record.data.value : null,
)
const item = computed(
  () =>
    detail.value?.item ??
    (record.data.value && 'items' in record.data.value ? record.data.value.items[0] : null),
)
const queueKind =
  type === 'team_membership'
    ? 'team_invitations'
    : type === 'partner_request'
      ? 'partner_requests'
      : null
const relatedPage = computed(() => {
  const page = Number(route.query.related_page ?? 1)
  return Number.isInteger(page) && page > 0 && page <= 100000 ? page : 1
})
function loadRecord() {
  return record.load(`${type}:${key}`, () =>
    section
      ? $adminApi.entity(section, key, relatedPage.value)
      : $adminApi.activity({ entity_type: type, entity_key: key, page_size: 1 }),
  )
}
function loadQueue() {
  if (!queueKind) return
  return queue.load(`${type}:${key}`, () =>
    $adminApi.queue(queueKind, {
      entity_key: key,
      membership_status: type === 'team_membership' ? 'all' : undefined,
      page_size: 1,
    }),
  )
}
function refreshRecord() {
  void loadRecord()
  void loadQueue()
}
onMounted(refreshRecord)
watch(relatedPage, loadRecord)
</script>
<template>
  <div class="operations-page [overflow-wrap:anywhere]">
    <PageHeader
      title="Datensatz untersuchen"
      :description="entityPresentation(type).label + ' · Identität, Beziehungen und Arbeitsstand'"
    >
      <button
        class="button"
        :disabled="record.loading.value || queue.loading.value"
        @click="refreshRecord"
      >
        Datensatz aktualisieren
      </button>
    </PageHeader>
    <RequestState
      :loading="record.loading.value"
      :error="record.error.value"
      :has-data="!!record.data.value"
      @retry="loadRecord"
    />
    <EntityHero v-if="detail && section" :item="detail.item" :section="section" :inspector="true" />
    <DataListShell v-else-if="item && record.data.value" as="ul">
      <ActivityRow :item="item" :observed-at="record.data.value.observed_at" />
    </DataListShell>
    <EmptyState
      v-else-if="record.data.value && !record.loading.value"
      message="Für diesen Datensatz sind keine Grunddaten verfügbar."
    />
    <nav class="flex flex-wrap gap-x-4" aria-label="Inspector-Bereiche">
      <a href="#relations" class="action-link">Beziehungen</a>
      <a href="#findings" class="action-link">Befunde</a>
      <a href="#activity" class="action-link">Aktivität</a>
      <NuxtLink v-if="item?.action" :to="item.action.href" class="action-link"
        >Bestehende Detailansicht öffnen</NuxtLink
      >
    </nav>
    <RecordWorkflowSummary v-if="detail" :item="detail.item" />
    <div id="relations" class="scroll-mt-40 space-y-3">
      <GraphLink :entity-type="type" :entity-key="key" variant="compact" />
      <RecordRelations v-if="detail" :data="detail" :loading="record.loading.value" />
      <RecordSection v-if="queueKind" title="Beteiligte und Vorgang" surface="panel">
        <RequestState
          :loading="queue.loading.value"
          :error="queue.error.value"
          :has-data="!!queue.data.value"
          @retry="loadQueue"
        />
        <div v-for="entry in queue.data.value?.items" :key="entry.entity_key" class="space-y-3">
          <div class="flex flex-wrap gap-x-4">
            <NuxtLink :to="`/users/${entry.user_id}`" class="action-link"
              >Benutzer: {{ entry.user_name || entry.user_id }}</NuxtLink
            >
            <template v-if="entry.organization_id">
              <NuxtLink :to="`/organizations/${entry.organization_id}`" class="action-link"
                >Organisation: {{ entry.organization_name || entry.organization_id }}</NuxtLink
              >
              <GraphLink entity-type="organization" :entity-key="entry.organization_id" />
            </template>
            <template
              v-for="org in [
                { id: entry.from_organization_id, name: entry.from_organization_name },
                { id: entry.to_organization_id, name: entry.to_organization_name },
              ]"
              :key="org.id ?? ''"
            >
              <NuxtLink v-if="org.id" :to="`/organizations/${org.id}`" class="action-link">{{
                org.name || org.id
              }}</NuxtLink>
              <GraphLink v-if="org.id" entity-type="organization" :entity-key="org.id" />
            </template>
          </div>
          <CompactFacts
            :items="[
              { label: 'Erstellt', value: dateTime(entry.created_at) },
              ...(type === 'team_membership'
                ? [
                    { label: 'Eingeladen', value: dateTime(entry.invited_at) },
                    { label: 'Beigetreten', value: entry.has_joined },
                  ]
                : []),
            ]"
          />
          <p v-if="type === 'team_membership'" class="operations-meta">
            Einladungszeit und Mitgliedsstatus sind belegt; ein Beitrittszeitpunkt ist nicht
            verfügbar.
          </p>
          <NuxtLink
            :to="{
              path: `/queues/${queueKind}`,
              query: {
                entity_key: key,
                membership_status: type === 'team_membership' ? 'all' : undefined,
              },
            }"
            class="action-link"
            >Vorgang in der Arbeitsliste öffnen</NuxtLink
          >
        </div>
        <EmptyState
          v-if="queue.data.value && !queue.data.value.items.length"
          compact
          message="Kein Vorgang zu diesem Datensatz verfügbar."
        />
      </RecordSection>
      <EmptyState
        v-else-if="!section"
        compact
        message="Eine Beziehungsliste ist hier nicht verfügbar. Belegte Terminbeziehungen lassen sich im Beziehungsgraph prüfen."
      />
    </div>
    <div id="findings" class="scroll-mt-40">
      <EntityFindings :entity-type="type" :entity-key="key" />
    </div>
    <div id="activity" class="scroll-mt-40 space-y-3">
      <EntityTimeline v-if="timelineType" :entity-type="timelineType" :entity-key="key" compact />
      <RecordSection v-else title="Aktivität"
        ><EmptyState
          compact
          message="Ein zusammengeführter Verlauf ist für diese Objektart nicht verfügbar."
      /></RecordSection>
      <NuxtLink
        :to="{ path: '/activity', query: { entity_type: type, entity_key: key } }"
        class="action-link"
        >Neuanlage in Aktivität öffnen</NuxtLink
      >
    </div>
    <RecordSection title="Weitere Betriebsdaten" surface="subtle">
      <p class="type-body">
        Worker-Gesundheit und Social-Publishing-Bezüge sind für diesen Datensatz nicht verfügbar.
      </p>
      <p v-if="type === 'organization' || type === 'venue'" class="type-body">
        Belegte Standortprüfungen stehen im Verlauf. Eine vollständige, nach Datensatz gefilterte
        Geocoding-Liste ist nicht verfügbar.
      </p>
      <NuxtLink
        v-if="type === 'organization' || type === 'venue'"
        :to="{ path: '/geocoding', query: { entity_type: type } }"
        class="action-link"
        >Alle Standortprüfungen dieser Objektart</NuxtLink
      >
      <NuxtLink to="/social-publishing" class="action-link"
        >Social Publishing – Verfügbarkeit</NuxtLink
      >
    </RecordSection>
    <TechnicalInfoBar :items="[{ label: 'Entity Key', value: key, mono: true, copyable: true }]" />
  </div>
</template>
