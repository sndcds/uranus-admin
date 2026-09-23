<script lang="ts">
import { defineComponent, h } from 'vue'
import { markdownNodes } from '~/utils/markdown'

/** Only pass fields whose Markdown capability is verified in the source contract. */
export default defineComponent({
  props: { source: { type: String, required: true } },
  setup(props) {
    return () => h('div', { class: 'prose-admin' }, markdownNodes(props.source))
  },
})
</script>
