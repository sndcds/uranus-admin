import { createApp, defineComponent, h } from 'vue'
import AppIcon from '../../../app/components/AppIcon.vue'
import DataListShell from '../../../app/components/DataListShell.vue'
import EmptyState from '../../../app/components/EmptyState.vue'
import SectionHeader from '../../../app/components/SectionHeader.vue'
import RequestState from '../../../app/components/RequestState.vue'
import SeverityBadge from '../../../app/components/SeverityBadge.vue'
import { timelineFixture } from '../entities'
import Showcase from './Showcase.vue'
import './showcase.css'
// Test-only Nuxt adapters: no network requests and no application route.
Object.assign(globalThis, {
  useRoute: () => ({ path: '/component-review', fullPath: '/component-review', query: {} }),
  useNuxtApp: () => ({
    $adminApi: {
      timeline: async () => timelineFixture('user'),
      subscribeViewReads: () => () => {},
    },
  }),
})
const app = createApp(Showcase)
for (const [name, component] of Object.entries({
  AppIcon,
  DataListShell,
  EmptyState,
  SectionHeader,
  RequestState,
  SeverityBadge,
}))
  app.component(name, component)
app.component(
  'NuxtLink',
  defineComponent({
    props: { to: { type: String, required: true } },
    setup:
      (props, { slots }) =>
      () =>
        h('a', { href: props.to }, slots.default?.()),
  }),
)
app.mount('#app')
