<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'

withDefaults(
  defineProps<{
    /** Whether the table it explains also paints the started/stopped dots. */
    showRunState?: boolean
  }>(),
  { showRunState: true }
)

const { t } = useI18n()
</script>

<template>
  <!-- Indented by the card's corner radius: flush with the card box the legend
       reads as sticking out, because the border curves away at this height. -->
  <div class="flex flex-wrap items-center gap-x-6 gap-y-2 pl-2 text-xs text-gray-warm-500">
    <span class="flex items-center gap-1.5">
      <Icon name="eye" size="xs" stroke-color="gray-warm-500" />
      {{ t('views.deployments.visibility.visible') }}
    </span>
    <span class="flex items-center gap-1.5">
      <Icon name="eye-off" size="xs" stroke-color="gray-warm-500" />
      {{ t('views.deployments.visibility.hidden') }}
    </span>
    <span class="flex items-center gap-1.5">
      <Icon name="minus" size="xs" stroke-color="gray-warm-500" />
      {{ t('views.deployments.visibility.mixed') }}
    </span>
    <template v-if="showRunState">
      <span class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-full bg-success-600 ring-2 ring-success-200" />
        {{ t('views.deployment-visibility.legend.started') }}
      </span>
      <span class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-full bg-gray-warm-300" />
        {{ t('views.deployment-visibility.legend.stopped') }}
      </span>
    </template>
  </div>
</template>
