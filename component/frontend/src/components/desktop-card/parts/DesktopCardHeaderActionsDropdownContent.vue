<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4/'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import { DropdownMenuGroup, DropdownMenuItem } from '@/components/ui/dropdown-menu'

const { t } = useI18n()

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
  changeImage: []
  showStorageModal: []
}>()
</script>

<template>
  <DropdownMenuGroup>
    <template v-if="props.desktop.status === DesktopStatusEnum.STOPPED">
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
      <DropdownMenuItem @click="emit('changeImage')">
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="image-plus"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.change-image') }}
        </Button>
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('showStorageModal')">
        <Button
          size="sm"
          class="mr-2 w-full justify-start"
          hierarchy="link-gray"
          icon="hard-drive"
          icon-size="md"
        >
          {{ t('components.desktops.desktop-card.actions.storage') }}
        </Button>
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('createTemplate')">
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
        v-if="
          props.desktop.status === DesktopStatusEnum.STOPPED &&
          !props.desktop.tag &&
          props.desktop.needs_booking === true
        "
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
      v-if="props.desktop.status === DesktopStatusEnum.STOPPED && !props.desktop.tag"
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
