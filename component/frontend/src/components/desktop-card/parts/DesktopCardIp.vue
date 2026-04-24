<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Icon, CopyIcon } from '@/components/icon'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

const { t } = useI18n()

interface Props {
  desktopStatus: string
  desktopIp?: string | null
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div class="text-base-white text-sm font-medium flex items-center gap-2">
    <template v-if="props.desktopStatus === DesktopStatusEnum.WAITING_IP">
      <Icon
        name="loading-02"
        size="md"
        class="motion-safe:animate-[spin_2s_linear_infinite]"
        stroke-color="base-white"
      />
      {{ t('components.desktops.desktop-card.status.waitingip.text') }}
    </template>
    <template v-else-if="props.desktopIp">
      <i18n-t keypath="components.desktops.desktop-card.ip-address">
        <template #ip>
          <span class="font-mono">{{ props.desktopIp }}</span>
          <CopyIcon :value="props.desktopIp" size="sm" stroke-color="base-white" />
        </template>
      </i18n-t>
    </template>
  </div>
</template>
