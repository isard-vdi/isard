<script setup lang="ts">
import { computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import {
  getUserConfigOptions,
  getDesktopBastionLegacyOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { UserDesktop, BastionDirectViewerResponse } from '@/gen/oas/apiv4/'

import { Icon, CopyIcon } from '@/components/icon'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import { CARD_SIZE_INJECTION_KEY, cardOverlayPaddingVariants } from '..'

const { t } = useI18n()

interface Props {
  // Desktop card: the bastion target is fetched here and the URLs are built
  // from the user config.
  desktop?: UserDesktop
  // Direct viewer: URLs come ready-made from get-details, because that view
  // is unauthenticated and can't read the config needed to build them.
  bastion?: BastionDirectViewerResponse
}

const props = defineProps<Props>()
const emit = defineEmits<{ showBastionModal: [] }>()

const size = inject(CARD_SIZE_INJECTION_KEY, 'lg')

const isCardMode = computed(() => !!props.desktop)

// Both queries need a logged-in user, so they only run in card mode.
const { data: userConfig } = useQuery({ ...getUserConfigOptions(), enabled: isCardMode })
const { data: target, isPending } = useQuery({
  ...getDesktopBastionLegacyOptions({ path: { desktop_id: props.desktop?.id ?? '' } }),
  enabled: isCardMode
})

// A disabled query stays pending forever, so only card mode can use its state.
const isLoading = computed(() => (isCardMode.value ? isPending.value : !props.bastion))

const httpEnabled = computed(() =>
  isCardMode.value ? !!target.value?.http?.enabled : !!props.bastion?.http_enabled
)
const sshEnabled = computed(() =>
  isCardMode.value ? !!target.value?.ssh?.enabled : !!props.bastion?.ssh_enabled
)

// No target, or a target with both accesses disabled: nothing to connect to.
const hasAccess = computed(() => httpEnabled.value || sshEnabled.value)

// Subdomain shown in URLs: <id-with-last-dash-as-dot>.<bastion-domain>.
// Same logic the modal uses — keeps URLs consistent across surfaces.
const targetIdSubdomain = computed(() => {
  const id = target.value?.id
  if (!id) return ''
  const parts = id.split('-')
  return `${parts.slice(0, -1).join('-')}.${parts.slice(-1)[0]}`
})

// URLs are built from the first custom domain only; the bastion modal lists
// the whole set.
const httpsUrl = computed(() => {
  if (!isCardMode.value) return props.bastion?.https_url ?? ''
  if (!target.value) return ''
  const port = userConfig.value?.https_port === '443' ? '' : `:${userConfig.value?.https_port}`
  if (target.value.domains?.[0]) return `https://${target.value.domains[0]}${port}`
  return `https://${targetIdSubdomain.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})

const httpUrl = computed(() => {
  if (!isCardMode.value) return props.bastion?.http_url ?? ''
  if (!target.value) return ''
  const port = userConfig.value?.http_port === '80' ? '' : `:${userConfig.value?.http_port}`
  if (target.value.domains?.[0]) return `http://${target.value.domains[0]}${port}`
  return `http://${targetIdSubdomain.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})

const sshUrl = computed(() => {
  if (!isCardMode.value) return props.bastion?.ssh_command ?? ''
  if (!target.value) return ''
  const port =
    userConfig.value?.bastion_ssh_port === '22' ? '' : ` -p ${userConfig.value?.bastion_ssh_port}`
  return `ssh ${target.value.id}@${target.value.domains?.[0] || userConfig.value?.bastion_domain || window.location.hostname}${port}`
})
</script>

<template>
  <div :class="cardOverlayPaddingVariants({ size })" class="text-base-white text-start">
    <div class="flex items-center gap-2 mb-1.5">
      <Icon name="globe-04" size="sm" stroke-color="base-white" />
      <span class="text-[10px] font-bold uppercase tracking-wide truncate">
        {{ t('components.desktops.desktop-card.actions.bastion') }}
      </span>
    </div>

    <div v-if="isLoading" class="flex flex-col gap-1.5">
      <Skeleton class="bg-base-white/20 h-4 w-full" />
      <Skeleton class="bg-base-white/20 h-4 w-3/4" />
    </div>
    <div v-else-if="!hasAccess" class="text-[11px] text-base-white/80">
      {{ t('components.bastion-info-modal.no-bastion-configured') }}
    </div>
    <div v-else class="flex flex-col gap-1 text-xs">
      <div v-if="httpEnabled" class="flex items-center gap-1.5 min-w-0">
        <Icon name="globe-04" size="xs" stroke-color="base-white" class="shrink-0" />
        <code class="font-mono truncate flex-1 min-w-0">{{ httpsUrl }}</code>
        <a :href="httpsUrl" target="_blank" :title="httpsUrl" class="shrink-0">
          <Icon
            name="link-external-01"
            size="xs"
            stroke-color="base-white"
            class="cursor-pointer"
          />
        </a>
        <CopyIcon :value="httpsUrl" size="xs" stroke-color="base-white" class="shrink-0" />
      </div>
      <div v-if="httpEnabled" class="flex items-center gap-1.5 min-w-0">
        <span class="w-3 shrink-0" />
        <code class="font-mono truncate flex-1 min-w-0 text-base-white/70">{{ httpUrl }}</code>
        <CopyIcon :value="httpUrl" size="xs" stroke-color="base-white" class="shrink-0" />
      </div>
      <div v-if="sshEnabled" class="flex items-center gap-1.5 min-w-0">
        <Icon name="terminal-square" size="xs" stroke-color="base-white" class="shrink-0" />
        <code class="font-mono truncate flex-1 min-w-0">{{ sshUrl }}</code>
        <CopyIcon :value="sshUrl" size="xs" stroke-color="base-white" class="shrink-0" />
      </div>
    </div>

    <div class="flex justify-end mt-1.5">
      <Tooltip>
        <TooltipTrigger as-child>
          <Button
            hierarchy="link-gray"
            size="sm"
            class="h-6! px-2! gap-1 bg-base-white/15 hover:bg-base-white/30 text-[10px] font-semibold text-base-white"
            @click="emit('showBastionModal')"
          >
            {{ t('components.desktops.desktop-card.overlay.expand') }}
            <Icon name="expand-04" size="xs" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.desktops.desktop-card.overlay.expand-tooltip')" />
      </Tooltip>
    </div>
  </div>
</template>
