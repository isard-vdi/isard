<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Icon } from '../icon'
// A value on the summary card, flagged when the forms below have moved it.
// The icon that labels the value goes in the default slot so the flag can wrap
// both; `changed` comes back as a slot prop for the icon to follow the accent.

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
    :class="[
      'flex items-center [&_svg]:shrink-0',
      changed ? 'bg-brand-100 text-brand-700 px-2 py-1 rounded-md' : ''
    ]"
    :title="changed ? t('components.domain-summary.changed') : undefined"
  >
    <slot :changed="changed" />
    <span
      :class="[
        'text-sm',
        changed ? 'rounded-md bg-brand-100 font-semibold ml-2' : 'ml-2 font-semibold'
      ]"
      >{{ value }}</span
    >
    <Icon v-if="changed" name="dot" size="xs" stroke-color="brand-700" class="ml-1" />
  </span>
</template>
