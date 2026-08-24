<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// A value on the summary card, flagged when the forms below have moved it.

withDefaults(
  defineProps<{
    value: string
    changed?: boolean
  }>(),
  {
    changed: false
  }
)

const { t } = useI18n()
</script>

<template>
  <span
    :class="['text-sm', changed ? 'font-bold text-brand-700' : 'font-semibold']"
    :title="changed ? t('components.domain-summary.changed') : undefined"
    >{{ value }}</span
  >
</template>
