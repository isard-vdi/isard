<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'

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
  </div>
</template>
