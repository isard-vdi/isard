<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// A value on the summary card, flagged when the forms below have moved it.

withDefaults(
  defineProps<{
    value: string
    /** What the field held before the edit, shown next to the new value. */
    previous?: string | null
    changed?: boolean
    /** The field held it before the edit and no longer does. */
    removed?: boolean
  }>(),
  {
    previous: null,
    changed: false,
    removed: false
  }
)

const { t } = useI18n()
</script>

<template>
  <span class="flex items-baseline gap-1.5">
    <span
      v-if="removed"
      class="text-sm font-regular text-gray-warm-400 line-through"
      :title="t('components.domain-summary.removed')"
      >{{ value }}</span
    >
    <template v-else>
      <span
        :class="['text-sm', changed ? 'font-bold text-brand-700' : 'font-semibold']"
        :title="changed ? t('components.domain-summary.changed') : undefined"
        >{{ value }}</span
      >
      <span
        v-if="changed && previous"
        class="text-xs font-regular text-gray-warm-400 line-through"
        >{{ previous }}</span
      >
    </template>
  </span>
</template>
