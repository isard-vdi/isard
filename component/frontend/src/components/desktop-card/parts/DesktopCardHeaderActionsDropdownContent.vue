<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4/'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import { DropdownMenuGroup, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { hasAdvancedOptions } from '@/components/desktop-card/advanced-options-modal/options'

import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()

const canSeeAdvancedOptions = computed(() => hasAdvancedOptions(authStore.user?.role_id))

interface Props {
  desktop: UserDesktop
  networks?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  networks: false
})

// `showInfoModal` and `showBastionModal` were promoted to dedicated icon
// buttons in DesktopCardHeaderActions; the dropdown no longer emits them.
const emit = defineEmits<{
  editDesktop: []
  showDeleteModal: []
  showDirectLinkModal: []
  showRecreateModal: []
  createTemplate: []
  bookDesktop: []
  showStorageModal: []
}>()

const isManageable = computed(
  () =>
    props.desktop.status === DesktopStatusEnum.STOPPED ||
    props.desktop.status === DesktopStatusEnum.FAILED
)
</script>

<template>
  <DropdownMenuGroup>
    <template v-if="isManageable">
      <DropdownMenuItem @click="emit('editDesktop')">
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="edit-01"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.edit') }}
        </Button>
      </DropdownMenuItem>
      <DropdownMenuItem v-if="canSeeAdvancedOptions" @click="emit('showStorageModal')">
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="settings-02"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.advanced-options') }}
        </Button>
      </DropdownMenuItem>
      <DropdownMenuItem
        v-if="props.desktop.status === DesktopStatusEnum.STOPPED"
        @click="emit('createTemplate')"
      >
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="colors"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.template') }}
        </Button>
      </DropdownMenuItem>
      <DropdownMenuItem
        v-if="!props.desktop.tag && props.desktop.needs_booking === true"
        @click="emit('bookDesktop')"
      >
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="calendar-check-02"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.book') }}
        </Button>
      </DropdownMenuItem>
    </template>
    <DropdownMenuItem @click="emit('showDirectLinkModal')">
      <Button
        size="sm"
        class="mr-2 w-full justify-start"
        hierarchy="link-gray"
        icon="link-01"
        icon-size="md"
      >
        {{ t('components.desktops.desktop-card.actions.direct-link') }}
      </Button>
    </DropdownMenuItem>
    <DropdownMenuItem
      v-if="props.desktop.tag && props.desktop.permissions?.includes('recreate')"
      @click="emit('showRecreateModal')"
    >
      <Button
        size="sm"
        class="mr-2 w-full justify-start"
        hierarchy="link-gray"
        icon="refresh-cw-01"
        icon-size="md"
      >
        {{ t('components.desktops.desktop-card.actions.recreate') }}
      </Button>
    </DropdownMenuItem>
    <DropdownMenuItem
      v-if="isManageable && !props.desktop.tag"
      class="hover:bg-error-50 focus:bg-error-50"
      @click="emit('showDeleteModal')"
    >
      <Button
        size="sm"
        class="mr-2 w-full justify-start text-error-700"
        hierarchy="link-gray"
        icon="trash-04"
        icon-size="md"
      >
        {{ t('components.desktops.desktop-card.actions.delete') }}
      </Button>
    </DropdownMenuItem>
  </DropdownMenuGroup>
</template>
