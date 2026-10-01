<script setup lang="ts">
defineProps<{ side: 'left' | 'right' }>()
</script>
<template>
  <div
    class="research-city pointer-events-none absolute"
    :class="`research-city-${side}`"
    aria-hidden="true"
  >
    <svg viewBox="0 0 280 290" fill="none" class="h-full w-full text-blue-200">
      <ellipse cx="145" cy="254" rx="135" ry="17" fill="currentColor" opacity=".18" />
      <g stroke="currentColor" stroke-width="1.5" opacity=".7">
        <path d="M9 242H276" />
        <path d="M32 266H116M146 273H244" opacity=".3" />
      </g>
      <template v-if="side === 'left'">
        <path
          d="M-16 34C71 8 156 69 193 163"
          stroke="currentColor"
          stroke-width="2"
          stroke-dasharray="6 6"
        />
        <g fill="currentColor" opacity=".42">
          <path
            d="M15 241V208L35 187L55 208V241ZM61 241V167L83 143L106 167V241ZM110 241V191L138 169L166 191V241Z"
          />
          <path d="M73 152V122L83 74L94 122V152Z" />
          <ellipse cx="197" cy="205" rx="14" ry="27" />
          <ellipse cx="242" cy="184" rx="20" ry="37" />
          <path d="M195 214H198V243H195ZM240 210H243V243H240Z" />
        </g>
        <g stroke="white" stroke-width="6" opacity=".8">
          <path d="M28 218H41M75 177H92M75 197H92M75 217H92M125 203H151M125 223H151" />
        </g>
      </template>
      <template v-else>
        <path
          d="M60 34C141 32 193 72 202 163M60 141C94 74 169 33 249 76"
          stroke="currentColor"
          stroke-width="2"
          stroke-dasharray="6 6"
        />
        <g fill="currentColor" opacity=".42">
          <path
            d="M69 241V187L94 164L120 187V241ZM125 241V112L149 79L173 112V241ZM178 241V169L208 143L237 169V241Z"
          />
          <ellipse cx="33" cy="199" rx="13" ry="23" />
          <ellipse cx="33" cy="171" rx="10" ry="26" />
          <path d="M31 214H34V243H31Z" />
        </g>
        <g stroke="white" stroke-width="6" opacity=".8">
          <path
            d="M83 204H106M83 224H106M140 122H158M140 147H158M140 172H158M140 197H158M140 222H158M192 184H220M192 209H220"
          />
        </g>
      </template>
    </svg>
    <span
      class="research-city-icon absolute grid h-14 w-14 place-items-center rounded-full bg-blue-100/80 text-blue-600"
      :class="side === 'left' ? 'left-32 top-1' : 'left-10 top-1'"
    >
      <AppIcon :name="side === 'left' ? 'pin' : 'calendar'" :size="28" />
    </span>
    <span
      v-if="side === 'right'"
      class="research-city-icon absolute right-0 top-16 grid h-14 w-14 place-items-center rounded-full bg-violet-100/70 text-violet-600"
    >
      <AppIcon name="users" :size="28" />
    </span>
  </div>
</template>
<style scoped>
.research-city {
  display: none;
}
@media (min-width: 768px) {
  .research-city {
    display: block;
    top: 54px;
    width: 180px;
    height: 290px;
    opacity: 0.55;
  }
  .research-city-left {
    left: -24px;
  }
  .research-city-right {
    right: -8px;
  }
  .research-city-icon {
    transform: scale(0.75);
  }
}
@media (min-width: 1280px) {
  .research-city {
    width: 280px;
    opacity: 1;
  }
  .research-city-left {
    left: -40px;
  }
  .research-city-right {
    right: 0;
  }
  .research-city-icon {
    transform: none;
  }
}
</style>
