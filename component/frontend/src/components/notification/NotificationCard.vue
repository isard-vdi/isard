<script setup lang="ts">
import type { NotificationFlatItem } from '@/gen/oas/apiv4'
import DOMPurify from 'dompurify'
import { computed } from 'vue'
import { Icon } from '../icon'

type HeadingLevel = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'

interface Props {
  notification: NotificationFlatItem
  headingLevel?: HeadingLevel
}

const props = withDefaults(defineProps<Props>(), {
  headingLevel: 'h2'
})

// The notification body/footer are server-provided HTML rendered via v-html;
// sanitize them with DOMPurify to prevent stored-XSS.
const sanitizedBody = computed(() =>
  props.notification.body ? DOMPurify.sanitize(props.notification.body) : ''
)
const sanitizedFooter = computed(() =>
  props.notification.footer ? DOMPurify.sanitize(props.notification.footer) : ''
)
</script>

<template>
  <article
    class="flex flex-col gap-2 p-5 pl-3 bg-base-white w-full border border-gray-warm-300 rounded-lg overflow-hidden transition-transform duration-300 hover:translate-x-2"
  >
    <div class="flex gap-4 items-center">
      <div class="self-stretch border-r border-brand-200 flex items-center pr-3">
        <Icon
          name="bell-01"
          size="lg"
          class="shrink-0 bg-brand-200 p-1 rounded-full"
          stroke-color="brand-700"
          aria-hidden="true"
        />
      </div>
      <div class="w-full">
        <component :is="props.headingLevel" class="font-bold text-lg text-brand-700">
          {{ notification.title }}
        </component>
        <!-- eslint-disable vue/no-v-html -- content sanitized via DOMPurify -->
        <div v-if="sanitizedBody" class="text-md mb-2" v-html="sanitizedBody" />
        <footer
          v-if="sanitizedFooter"
          class="w-fit ml-auto border-t border-gray-warm-200 pt-1 pl-7 text-right text-sm font-semibold text-gray-warm-500"
          v-html="sanitizedFooter"
        ></footer>
        <!-- eslint-enable vue/no-v-html -->
      </div>
    </div>
  </article>
</template>
