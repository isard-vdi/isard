<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4/'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import { DropdownMenuGroup, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { hasAdvancedOptions } from '@/components/desktop-card/advanced-options-modal/options'

import { useAuthStore } from '@/stores/auth'
import { isNotUser } from '@/lib/auth'

const { t } = useI18n()
const authStore = useAuthStore()

interface Props {
  desktop: UserDesktop
  networks?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  networks: false
})

// `showInfoModal` and `showBastionModal` were promoted to dedicated icon
// buttons in DesktopCardHeaderActions; the dropdown no longer emits them.
type ActionEvent =
  | 'editDesktop'
  | 'showStorageModal'
  | 'createTemplate'
  | 'bookDesktop'
  | 'showDirectLinkModal'
  | 'showRecreateModal'
  | 'showDeleteModal'

const emit = defineEmits<(e: ActionEvent) => void>()

interface Action {
  event: ActionEvent
  labelKey: string
  icon: string
  when: boolean
  danger?: boolean
}

const isManageable = computed(
  () =>
    props.desktop.status === DesktopStatusEnum.STOPPED ||
    props.desktop.status === DesktopStatusEnum.FAILED
)

const role = computed(() => authStore.user?.role_id)

// A deployment desktop is shaped from its deployment, the deployment owner's
// own desktop included; recreate is the only entry the owner can hand out.
const isStandalone = computed(() => !props.desktop.tag)

const actions = computed<Action[]>(() =>
  (
    [
      {
        event: 'editDesktop',
        labelKey: 'components.desktops.desktop-card.actions.edit',
        icon: 'edit-01',
        when: isManageable.value && isStandalone.value
      },
      {
        event: 'showStorageModal',
        labelKey: 'components.desktops.desktop-card.actions.advanced-options',
        icon: 'settings-02',
        when: isManageable.value && isStandalone.value && hasAdvancedOptions(role.value)
      },
      {
        event: 'createTemplate',
        labelKey: 'components.desktops.desktop-card.actions.template',
        icon: 'colors',
        when:
          props.desktop.status === DesktopStatusEnum.STOPPED &&
          isStandalone.value &&
          isNotUser(role.value)
      },
      {
        event: 'bookDesktop',
        labelKey: 'components.desktops.desktop-card.actions.book',
        icon: 'calendar-check-02',
        when: isManageable.value && isStandalone.value && props.desktop.needs_booking === true
      },
      {
        event: 'showDirectLinkModal',
        labelKey: 'components.desktops.desktop-card.actions.direct-link',
        icon: 'link-01',
        when: isStandalone.value
      },
      {
        event: 'showRecreateModal',
        labelKey: 'components.desktops.desktop-card.actions.recreate',
        icon: 'refresh-cw-01',
        when: Boolean(props.desktop.tag && props.desktop.permissions?.includes('recreate'))
      },
      {
        event: 'showDeleteModal',
        labelKey: 'components.desktops.desktop-card.actions.delete',
        icon: 'trash-04',
        when: isManageable.value && isStandalone.value,
        danger: true
      }
    ] satisfies Action[]
  ).filter((action) => action.when)
)
</script>

<template>
  <DropdownMenuGroup>
    <DropdownMenuItem
      v-for="action in actions"
      :key="action.event"
      :class="{ 'hover:bg-error-50 focus:bg-error-50': action.danger }"
      @click="emit(action.event)"
    >
      <Button
        size="sm"
        class="mr-2 w-full justify-start"
        :class="{ 'text-error-700': action.danger }"
        hierarchy="link-gray"
        :icon="action.icon"
        icon-size="md"
      >
        {{ t(action.labelKey) }}
      </Button>
    </DropdownMenuItem>
  </DropdownMenuGroup>
</template>
