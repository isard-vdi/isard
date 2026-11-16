<script setup lang="ts">
import { computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'
import { describeApiError } from '@/lib/api-errors'
import {
  clearDesktopTimeouts,
  desktopTimeouts,
  highestDesktopTimeoutLevel,
  removeDesktopTimeoutsOf,
  type DesktopTimeoutLevel,
  type DesktopTimeoutWarning
} from '@/lib/desktop-timeout'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/stores/session'
import { extendDesktopTimeoutMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import shutdownWarning from '@/assets/img/modal/desktop-shutdown-warning.svg'
import shutdownDanger from '@/assets/img/modal/desktop-shutdown-danger.svg'
import type { Client } from '@/gen/oas/apiv4/client'

interface Props {
  client?: Client
  extendable?: boolean
}

const { client, extendable = true } = defineProps<Props>()

const { t, te, d } = useI18n()
const sessionStore = useSessionStore()

const levelDotClasses: Record<DesktopTimeoutLevel, string> = {
  info: 'bg-info-modal',
  warning: 'bg-warning-modal',
  danger: 'bg-error-600'
}

const warnings = computed(() =>
  [...desktopTimeouts.value].sort(
    (a, b) => new Date(a.stopsAt).getTime() - new Date(b.stopsAt).getTime()
  )
)

const single = computed(() => (warnings.value.length === 1 ? warnings.value[0] : null))

// The session modal always sits on top, so a warning opened under it could not be seen or
// answered; warnings wait in the list until it closes.
const open = computed(() => warnings.value.length > 0 && !sessionStore.modalOpen)

const describe = (warning: DesktopTimeoutWarning) =>
  t('components.desktop-timeout-modal.description', {
    name: warning.name,
    date: d(warning.stopsAt, { timeStyle: 'short' })
  })

const description = computed(() =>
  single.value
    ? describe(single.value)
    : t('components.desktop-timeout-modal.description-multiple', { count: warnings.value.length })
)

const canExtend = (warning: DesktopTimeoutWarning) =>
  extendable && warning.desktopId !== null && warning.extendMinutes !== null

const {
  mutate: extendTimeout,
  isPending: isExtending,
  variables: extending
} = useMutation({
  ...extendDesktopTimeoutMutation({ client }),
  onSuccess: (_data, variables) => removeDesktopTimeoutsOf(variables.path.desktop_id),
  onError: (error) => toast.error(describeApiError(error, { t, te }, 'extend-desktop'))
})

const isExtendingDesktop = (warning: DesktopTimeoutWarning) =>
  isExtending.value && extending.value?.path.desktop_id === warning.desktopId

const onExtend = (warning: DesktopTimeoutWarning) => {
  if (warning.desktopId) extendTimeout({ path: { desktop_id: warning.desktopId } })
}

const onUpdateOpen = (value: boolean) => {
  if (!value) clearDesktopTimeouts()
}

onUnmounted(clearDesktopTimeouts)
</script>

<template>
  <AlertModal
    :open="open"
    :size="single ? 'md' : 'lg'"
    :level="highestDesktopTimeoutLevel(warnings)"
    :image="highestDesktopTimeoutLevel(warnings) === 'danger' ? shutdownDanger : shutdownWarning"
    :title="t('components.desktop-timeout-modal.title')"
    :description="description"
    :close-on-backdrop-click="!isExtending"
    :show-close-button="!isExtending"
    @update:open="onUpdateOpen"
  >
    <template v-if="!single" #description>
      <ul class="mt-2 flex flex-col divide-y divide-gray-warm-200">
        <li v-for="warning in warnings" :key="warning.key" class="flex items-center gap-3 py-3">
          <span
            aria-hidden="true"
            :class="cn('size-2.5 shrink-0 rounded-full', levelDotClasses[warning.level])"
          />
          <span class="grow wrap-break-word">{{ describe(warning) }}</span>
          <Button
            v-if="canExtend(warning)"
            size="sm"
            hierarchy="secondary-color"
            class="shrink-0"
            :disabled="isExtending"
            @click="onExtend(warning)"
          >
            <Spinner v-if="isExtendingDesktop(warning)" size="sm" class="mr-1" />
            {{
              t('components.desktop-timeout-modal.extend-time', { minutes: warning.extendMinutes })
            }}
          </Button>
        </li>
      </ul>
    </template>
    <template v-if="single && canExtend(single)" #footer>
      <Button size="lg" hierarchy="primary" :disabled="isExtending" @click="onExtend(single)">
        <Spinner v-if="isExtending" size="sm" class="mr-1" />
        {{ t('components.desktop-timeout-modal.extend-time', { minutes: single.extendMinutes }) }}
      </Button>
    </template>
  </AlertModal>
</template>
