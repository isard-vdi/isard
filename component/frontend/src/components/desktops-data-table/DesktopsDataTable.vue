<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop } from '@/gen/oas/apiv4/'

import {
  desktopNeedsBooking,
  desktopActionsData,
  desktopHasMenuActions,
  desktopNotificationText
} from '@/lib/desktops'
import { copyToClipboard } from '@/lib/utils'

import {
  DesktopCellImage,
  DesktopCellName,
  DesktopCellStatus,
  DesktopCellMainActionsButton
} from '.'
import { Button } from '@/components/ui/button'
import { DataTable } from '@/components/data-table'
import { Progress } from '@/components/ui/progress'
import { TruncatedText } from '@/components/truncated-text'
import { DesktopCardHeaderActionsDropdownContent } from '@/components/desktop-card'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ViewerSelect } from '@/components/viewer-select'

interface Props {
  desktops: ApiSchemasDomainsDesktopsUserDesktop[]
  preferedViewers: Record<string, string>
}

const { t, d } = useI18n()

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  // --- Main actions ---
  desktopStart: [ApiSchemasDomainsDesktopsUserDesktop]
  desktopStop: [ApiSchemasDomainsDesktopsUserDesktop]
  desktopUpdateStatus: [ApiSchemasDomainsDesktopsUserDesktop]
  desktopAbortOperation: [ApiSchemasDomainsDesktopsUserDesktop]
  desktopFetchBooking: [ApiSchemasDomainsDesktopsUserDesktop]
  // desktop*: [ApiSchemasDomainsDesktopsUserDesktop]
  // --- Viewers ---
  openViewer: [{ dktp: ApiSchemasDomainsDesktopsUserDesktop; viewer: string }]
  // --- Modals ---
  fetchNetworks: [ApiSchemasDomainsDesktopsUserDesktop]
  showNetworksModal: [ApiSchemasDomainsDesktopsUserDesktop]
  showInfoModal: [ApiSchemasDomainsDesktopsUserDesktop]
  showBastionModal: [ApiSchemasDomainsDesktopsUserDesktop]
  showDirectLinkModal: [ApiSchemasDomainsDesktopsUserDesktop]
  showDeleteModal: [ApiSchemasDomainsDesktopsUserDesktop]
  showRecreateModal: [ApiSchemasDomainsDesktopsUserDesktop]
  // show*Modal: [ApiSchemasDomainsDesktopsUserDesktop]
  // --- Redirects ---
  editDesktop: [ApiSchemasDomainsDesktopsUserDesktop]
  createTemplate: [ApiSchemasDomainsDesktopsUserDesktop]
  bookDesktop: [ApiSchemasDomainsDesktopsUserDesktop]
  showStorageModal: [ApiSchemasDomainsDesktopsUserDesktop]
  // goTo*: [ApiSchemasDomainsDesktopsUserDesktop]
}>()

const ACTION_SLOT_CLASS = 'flex min-h-9.5 w-full items-center'

// How many rows fit without turning the page into a long scroll. Read once,
// when the table is created
const SHORT_VIEWPORT_HEIGHT = 1080
const DEFAULT_PAGE_SIZE = window.innerHeight <= SHORT_VIEWPORT_HEIGHT ? 10 : 20

const asDesktop = (row: unknown) => row as ApiSchemasDomainsDesktopsUserDesktop

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
    width: 'minmax(128px, 1fr)'
  },
  {
    name: t('components.desktops.data-table.headers.description'),
    key: 'description',
    sortable: true,
    width: 'minmax(112px, 1fr)'
  },
  {
    name: t('components.desktops.data-table.headers.status'),
    key: 'status',
    sortable: true,
    width: 'minmax(112px, 0.9fr)'
  },
  {
    name: t('components.desktops.data-table.headers.actions'),
    key: 'mainActions',
    width: 'minmax(168px, max-content)'
  },
  {
    name: t('components.desktops.data-table.headers.viewers'),
    key: 'viewers',
    width: 'minmax(188px, max-content)'
  },
  {
    name: '',
    key: 'actions',
    width: 'min-content'
  }
]
</script>

<template>
  <DataTable
    :headers="headers"
    :rows="props.desktops"
    :is-clickable="false"
    :page-size="DEFAULT_PAGE_SIZE"
    density="compact"
    cell-class="h-auto min-h-13"
    row-class="odd:bg-gray-warm-100/30 hover:bg-gray-warm-100"
  >
    <template #cell-image="{ row }">
      <DesktopCellImage
        v-for="desktop in [asDesktop(row)]"
        :key="desktop.id"
        size="sm"
        :desktop="desktop"
        @copy-to-clipboard="copyToClipboard"
      />
    </template>
    <template #cell-name="{ row }">
      <DesktopCellName
        v-for="desktop in [asDesktop(row)]"
        :key="desktop.id"
        dense
        :desktop-name="desktop.name"
        :notification-text="desktopNotificationText(desktop, t, d)"
      />
    </template>

    <template #cell-description="{ row }">
      <template v-for="desktop in [asDesktop(row)]" :key="desktop.id">
        <TruncatedText
          v-if="desktop.description"
          :title="desktop.description"
          class="text-xs text-gray-warm-600"
        />
      </template>
    </template>

    <template #cell-status="{ row }">
      <DesktopCellStatus v-for="desktop in [asDesktop(row)]" :key="desktop.id" :desktop="desktop" />
    </template>

    <template #cell-mainActions="{ row }">
      <div v-for="desktop in [asDesktop(row)]" :key="desktop.id" :class="ACTION_SLOT_CLASS">
        <div
          v-if="desktop.progress && desktop.progress.percentage !== undefined"
          class="select-none w-32"
        >
          <div class="flex justify-between text-xs mb-1">
            <span>{{ desktop.progress.size }}</span>
            <span>{{ desktop.progress.percentage }}%</span>
          </div>
          <Progress :model-value="desktop.progress.percentage" class="w-full"></Progress>
        </div>
        <DesktopCellMainActionsButton
          v-else
          :desktop="desktop"
          @desktop-start="emit('desktopStart', desktop)"
          @desktop-stop="emit('desktopStop', desktop)"
          @desktop-update-status="emit('desktopUpdateStatus', desktop)"
          @desktop-abort-operation="emit('desktopAbortOperation', desktop)"
          @desktop-fetch-booking="emit('desktopFetchBooking', desktop)"
          @show-delete-modal="emit('showDeleteModal', desktop)"
        />
      </div>
    </template>

    <template #cell-viewers="{ row }">
      <div v-for="desktop in [asDesktop(row)]" :key="desktop.id" :class="ACTION_SLOT_CLASS">
        <ViewerSelect
          v-show="desktopActionsData(desktop.status, desktopNeedsBooking(desktop)).viewers"
          :viewers="
            desktop.viewers?.map((viewer: string) => ({
              id: viewer,
              loading: viewer.includes('rdp') && !desktop.ip
            }))
          "
          :selected-viewer="props.preferedViewers[desktop.id]"
          button-size="sm"
          dense
          @open-viewer="
            (viewer) =>
              emit('openViewer', {
                dktp: desktop,
                viewer: viewer
              })
          "
        />
      </div>
    </template>

    <template #cell-actions="{ row }">
      <div
        v-for="desktop in [asDesktop(row)]"
        :key="desktop.id"
        class="flex flex-row items-center justify-end gap-1.5 w-full"
      >
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-gray"
              icon="info-circle"
              icon-size="sm"
              class="size-8 p-0"
              :aria-label="t('components.desktops.desktop-card.actions.info')"
              @click="emit('showInfoModal', desktop)"
            />
          </TooltipTrigger>
          <TooltipContent :title="t('components.desktops.desktop-card.actions.info')" />
        </Tooltip>

        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-gray"
              icon="modem-02"
              icon-size="sm"
              class="size-8 p-0"
              :aria-label="t('components.desktops.desktop-card.actions.networks')"
              @click="emit('showNetworksModal', desktop)"
            />
          </TooltipTrigger>
          <TooltipContent :title="t('components.desktops.desktop-card.actions.networks')" />
        </Tooltip>

        <Tooltip
          v-if="desktop.bastion_target?.http?.enabled || desktop.bastion_target?.ssh?.enabled"
        >
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-gray"
              icon="globe-04"
              icon-size="sm"
              class="size-8 p-0"
              :aria-label="t('components.desktops.desktop-card.actions.bastion-access')"
              @click="emit('showBastionModal', desktop)"
            />
          </TooltipTrigger>
          <TooltipContent :title="t('components.desktops.desktop-card.actions.bastion-access')" />
        </Tooltip>

        <Tooltip v-if="desktopHasMenuActions(desktop)">
          <TooltipTrigger as-child>
            <span class="inline-flex">
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button
                    hierarchy="secondary-gray"
                    icon="dots-vertical"
                    icon-size="sm"
                    class="size-8 p-0"
                    :aria-label="t('common.actions.more')"
                  />
                </DropdownMenuTrigger>

                <DropdownMenuContent
                  class="bg-white border border-gray-warm-300 rounded-lg"
                  align="end"
                >
                  <DesktopCardHeaderActionsDropdownContent
                    :desktop="desktop"
                    @edit-desktop="emit('editDesktop', desktop)"
                    @show-delete-modal="emit('showDeleteModal', desktop)"
                    @show-direct-link-modal="emit('showDirectLinkModal', desktop)"
                    @show-recreate-modal="emit('showRecreateModal', desktop)"
                    @create-template="emit('createTemplate', desktop)"
                    @book-desktop="emit('bookDesktop', desktop)"
                    @show-storage-modal="emit('showStorageModal', desktop)"
                  />
                </DropdownMenuContent>
              </DropdownMenu>
            </span>
          </TooltipTrigger>
          <TooltipContent :title="t('common.actions.more')" />
        </Tooltip>
      </div>
    </template>
  </DataTable>
</template>
