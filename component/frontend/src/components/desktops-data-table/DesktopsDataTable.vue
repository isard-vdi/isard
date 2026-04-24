<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UserDesktop } from '@/gen/oas/apiv4/'

import { desktopNeedsBooking, desktopActionsData, desktopNotificationText } from '@/lib/desktops'
import { copyToClipboard } from '@/lib/utils'

import {
  DesktopCellImage,
  DesktopCellName,
  DesktopCellStatus,
  DesktopCellMainActionsButton
} from '.'
import { Button } from '@/components/ui/button'
import { DataTable } from '@/components/data-table'
import { DesktopCardHeaderActionsDropdownContent } from '@/components/desktop-card'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent
} from '@/components/ui/dropdown-menu'
import { ViewerSelect } from '@/components/viewer-select'

interface Props {
  desktops: UserDesktop[]
  preferedViewers: Record<string, string>
}

const { t, d } = useI18n()

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  // --- Main actions ---
  desktopStart: [UserDesktop]
  desktopStop: [UserDesktop]
  desktopUpdateStatus: [UserDesktop]
  desktopAbortOperation: [UserDesktop]
  desktopFetchBooking: [UserDesktop]
  // desktop*: [UserDesktop]
  // --- Viewers ---
  openViewer: [{ dktp: UserDesktop; viewer: string }]
  // --- Modals ---
  fetchNetworks: [UserDesktop]
  showNetworksModal: [UserDesktop]
  showInfoModal: [UserDesktop]
  showBastionModal: [UserDesktop]
  showDirectLinkModal: [UserDesktop]
  showDeleteModal: [UserDesktop]
  showRecreateModal: [UserDesktop]
  // show*Modal: [UserDesktop]
  // --- Redirects ---
  editDesktop: [UserDesktop]
  createTemplate: [UserDesktop]
  // goTo*: [UserDesktop]
}>()

const headers = [
  {
    name: '',
    key: 'image',
    width: 'min-content'
  },
  {
    name: t('components.desktops.data-table.headers.name'),
    key: 'name',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-96))'
  },
  {
    name: t('components.desktops.data-table.headers.description'),
    key: 'description',
    sortable: true
  },
  {
    name: t('components.desktops.data-table.headers.status'),
    key: 'status',
    sortable: true,
    width: 'minmax(var(--spacing-48), var(--spacing-64))'
  },
  {
    name: t('components.desktops.data-table.headers.actions'),
    key: 'mainActions',
    width: 'minmax(var(--spacing-32), var(--spacing-48))'
  },
  {
    name: t('components.desktops.data-table.headers.viewers'),
    key: 'viewers',
    width: 'minmax(var(--spacing-64), var(--spacing-80))'
  },
  {
    name: '',
    key: 'actions',
    width: 'min-content'
  }
]
</script>

<template>
  <DataTable :headers="headers" :rows="props.desktops" :is-clickable="false">
    <template #cell-image="{ row }">
      <DesktopCellImage :desktop="row" @copy-to-clipboard="copyToClipboard" />
    </template>
    <template #cell-name="{ row }">
      <DesktopCellName
        :desktop-name="row.name"
        :notification-text="desktopNotificationText(row, t, d)"
      />
    </template>

    <template #cell-description="{ row }">
      <p class="text-sm text-muted-foreground line-clamp-3">
        {{ row.description }}
      </p>
    </template>

    <template #cell-status="{ row }">
      <DesktopCellStatus :desktop="row" />
    </template>

    <template #cell-mainActions="{ row }">
      <div v-if="row.progress && row.progress.percentage !== undefined" class="select-none w-48">
        <div class="flex justify-between text-xs mb-1">
          <span>{{ row.progress.size }}</span>
          <span>{{ row.progress.percentage }}%</span>
        </div>
        <Progress :model-value="row.progress.percentage" class="w-full"></Progress>
      </div>
      <template v-else>
        <DesktopCellMainActionsButton
          :desktop="row"
          @desktop-start="emit('desktopStart', row)"
          @desktop-stop="emit('desktopStop', row)"
          @desktop-update-status="emit('desktopUpdateStatus', row)"
          @desktop-abort-operation="emit('desktopAbortOperation', row)"
          @desktop-fetch-booking="emit('desktopFetchBooking', row)"
        />
      </template>
    </template>

    <template #cell-viewers="{ row }">
      <ViewerSelect
        v-show="desktopActionsData(row.status, desktopNeedsBooking(row)).viewers"
        :viewers="
          row.viewers?.map((viewer: string) => ({
            id: viewer,
            loading: viewer.includes('rdp') && !row.ip
          }))
        "
        :selected-viewer="props.preferedViewers[row.id]"
        class="ml-auto"
        @open-viewer="
          (viewer) =>
            emit('openViewer', {
              dktp: row,
              viewer: viewer
            })
        "
      />
    </template>

    <template #cell-actions="{ row }">
      <div class="flex flex-row items-center justify-end gap-2">
        <Button
          hierarchy="secondary-gray"
          icon="modem-02"
          class="aspect-square p-[10px]"
          @click="emit('showNetworksModal', row)"
        />

        <DropdownMenu>
          <DropdownMenuTrigger>
            <Button
              hierarchy="secondary-gray"
              icon="dots-vertical"
              class="aspect-square p-[10px]"
            />
          </DropdownMenuTrigger>

          <DropdownMenuContent class="bg-white border border-gray-warm-300 rounded-lg" align="end">
            <DesktopCardHeaderActionsDropdownContent
              :desktop="row"
              @show-info-modal="emit('showInfoModal', row)"
              @edit-desktop="emit('editDesktop', row)"
              @show-delete-modal="emit('showDeleteModal', row)"
              @show-bastion-modal="emit('showBastionModal', row)"
              @show-direct-link-modal="emit('showDirectLinkModal', row)"
              @show-recreate-modal="emit('showRecreateModal', row)"
              @create-template="emit('createTemplate', row)"
            />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </template>
  </DataTable>
</template>
