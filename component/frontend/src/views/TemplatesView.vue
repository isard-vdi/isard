<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'

import {
  getUserTemplatesApiV4ItemsTemplatesGetOptions,
  getUserSharedTemplatesApiV4ItemsTemplatesGetSharedGetOptions,
  checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions,
  checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { copyToClipboard } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem
} from '@/components/ui/context-menu'
import { TemplateDataTable } from '@/components/data-table'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import { Icon } from '@/components/icon'
import { QuotaExceededModal } from '@/components/modal'
import { TemplateDeleteModal } from '@/components/templates/template-delete-modal'
import { TemplateToDesktopModal } from '@/components/templates/template-to-desktop-modal'
import { TemplateToggleVisibilityModal } from '@/components/template-toggle-visibility'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toggleVariants } from '@/components/ui/toggle'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DomainInfoModal } from '@/components/desktops'
import { getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet } from '@/gen/oas/apiv4/'

const router = useRouter()
const queryClient = useQueryClient()
const { t } = useI18n()

const activeTab = ref<'user' | 'shared'>('user')

// Queries
const {
  isPending: userTemplatesIsPending,
  isError: userTemplatesIsError,
  error: userTemplatesError,
  data: userTemplates
} = useQuery(getUserTemplatesApiV4ItemsTemplatesGetOptions())

const {
  isFetching: sharedTemplatesIsFetching,
  isError: sharedTemplatesIsError,
  error: sharedTemplatesError,
  data: sharedTemplates,
  refetch: fetchSharedTemplates
} = useQuery({
  ...getUserSharedTemplatesApiV4ItemsTemplatesGetSharedGetOptions(),
  enabled: false // Lazy load when tab is clicked
})

// Table configuration
const tableHeaders = computed(() => {
  const baseHeaders = [
    { name: '', key: 'image', width: 'var(--spacing-48)' },
    {
      name: t('views.templates.table.headers.name'),
      key: 'name',
      width: 'minmax(var(--spacing-48), var(--spacing-80))'
    },
    {
      name: t('views.templates.table.headers.description'),
      key: 'description',
      width: 'minmax(var(--spacing-56), 1fr)'
    }
  ]

  if (activeTab.value === 'shared') {
    baseHeaders.push({
      name: t('views.templates.table.headers.owner'),
      key: 'owner',
      width: 'minmax(var(--spacing-48), var(--spacing-64))'
    })
  }

  baseHeaders.push({ name: '', key: 'actions', width: 'max-content' })
  return baseHeaders
})

const tableRows = computed(() => {
  const data = activeTab.value === 'user' ? userTemplates.value : sharedTemplates.value
  return data?.templates || []
})

const handleSharedTabClick = () => {
  if (!sharedTemplates.value) {
    fetchSharedTemplates()
  }
}

// Modal state - unified structure
interface ModalData {
  id: string
  name: string
}

const deleteModalData = ref<ModalData | null>(null)
const convertModalData = ref<ModalData | null>(null)
const visibilityModalData = ref<(ModalData & { action: 'hide' | 'show' }) | null>(null)

// Quota check
const quotaExceededModalData = ref<{
  title: string
  description: string
  cancelLabel: string
} | null>(null)
const templateCreationCheckIsPending = ref(false)
const desktopCreationCheckIsPending = ref(false)

const handleWithTemplateQuotaCheck = async (callback: () => void) => {
  templateCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    templateCreationCheckIsPending.value = false
    callback()
  } catch {
    templateCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.templates.quota-exceeded-modal.title'),
      description: t('components.templates.quota-exceeded-modal.description'),
      cancelLabel: t('components.templates.quota-exceeded-modal.cancel')
    }
  }
}

const handleWithDesktopQuotaCheck = async (callback: () => void) => {
  desktopCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    desktopCreationCheckIsPending.value = false
    callback()
  } catch {
    desktopCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.desktops.quota-exceeded-modal.title'),
      description: t('components.desktops.quota-exceeded-modal.description'),
      cancelLabel: t('components.desktops.quota-exceeded-modal.cancel')
    }
  }
}

// Template Info Modal
const showTemplateInfoModal = ref(false)
const {
  mutate: fetchAndOpenTemplateInfoModal,
  isPending: fetchTemplateDetailsIsPending,
  isError: fetchTemplateDetailsIsError,
  error: fetchTemplateDetailsError,
  data: templateDetails,
  variables: templateDetailsDesktopId,
  reset: resetTemplateDetails
} = useMutation({
  mutationFn: async (templateId: string) => {
    const { data } = await getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet({
      path: {
        template_id: templateId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess: () => {
    showTemplateInfoModal.value = true
  }
})
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="!!quotaExceededModalData"
    :title="quotaExceededModalData?.title ?? ''"
    :description="quotaExceededModalData?.description ?? ''"
    :cancel-label="quotaExceededModalData?.cancelLabel ?? ''"
    :cancel-to="{ name: 'templates' }"
    @close="quotaExceededModalData = null"
  />

  <TemplateDeleteModal
    v-if="deleteModalData"
    :open="true"
    :template-id="deleteModalData.id"
    :template-name="deleteModalData.name"
    @close="deleteModalData = null"
  />

  <TemplateToDesktopModal
    v-if="convertModalData"
    :open="true"
    :template-id="convertModalData.id"
    :template-name="convertModalData.name"
    @close="convertModalData = null"
  />

  <TemplateToggleVisibilityModal
    v-if="visibilityModalData"
    :open="true"
    :action="visibilityModalData.action"
    :data="visibilityModalData"
    @close="visibilityModalData = null"
  />

  <DomainInfoModal
    :open="showTemplateInfoModal"
    :domain-id="templateDetailsDesktopId"
    :name="templateDetails?.name || ''"
    :description="templateDetails?.description"
    :vcpu="templateDetails?.vcpu"
    :ram="templateDetails?.memory"
    :boot-order="templateDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="templateDetails?.disk_bus"
    :vga="templateDetails?.videos.map((vga) => vga.name)"
    :viewers="templateDetails?.viewers"
    :isos="templateDetails?.isos?.map((iso) => iso.name)"
    :reservables="templateDetails?.reservables?.vgpus"
    :kind="'template'"
    @close="
      () => {
        showTemplateInfoModal = false
        resetTemplateDetails()
      }
    "
  />

  <main class="w-full flex justify-center">
    <div class="flex flex-col gap-6 w-full max-w-480">
      <div v-if="userTemplatesIsError || sharedTemplatesIsError" class="text-center text-error-500">
        <pre v-if="userTemplatesError">{{ userTemplatesError }}</pre>
        <pre v-if="sharedTemplatesError">{{ sharedTemplatesError }}</pre>
      </div>

      <TemplateDataTable
        :headers="tableHeaders"
        :rows="tableRows"
        :loading="userTemplatesIsPending || sharedTemplatesIsFetching"
        :is-clickable="false"
      >
        <template #filters-left>
          <Tabs v-model="activeTab">
            <TabsList class="flex w-fit gap-[--spacing(1)] rounded-md">
              <TabsTrigger
                value="user"
                :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
              >
                <Icon name="user-03" stroke-color="currentColor" />
                {{ t('components.templates.template-type.owned') }}
              </TabsTrigger>
              <TabsTrigger
                value="shared"
                :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
                @click="handleSharedTabClick"
              >
                <Icon name="share-06" stroke-color="currentColor" />
                {{ t('components.templates.template-type.shared') }}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </template>

        <template #filters-right>
          <Button
            :icon="templateCreationCheckIsPending ? 'loading-02' : 'plus'"
            :icon-class="{
              'motion-safe:animate-[spin_2s_linear_infinite]': templateCreationCheckIsPending
            }"
            :disabled="templateCreationCheckIsPending"
            @click="handleWithTemplateQuotaCheck(() => router.push({ name: 'new-template' }))"
            >{{ t('views.templates.new-template') }}</Button
          >
        </template>

        <template #cell-image="{ row }">
          <div
            class="w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover relative"
            :style="{
              backgroundImage: `url(${row.image.url})`
            }"
          >
            <ContextMenu>
              <ContextMenuTrigger class="absolute top-0 bottom-0 left-0 w-1/4 rounded-l-2xl">
              </ContextMenuTrigger>
              <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
                <ContextMenuItem @click="copyToClipboard(row.id)">{{
                  t('components.templates.datatable.debug-options.copy-id')
                }}</ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          </div>
        </template>

        <template #cell-name="{ row }">
          <p class="text-sm font-semibold text-gray-warm-900 truncate">{{ row.name }}</p>
        </template>

        <template #cell-description="{ row }">
          <p class="text-xs font-medium text-gray-warm-600 line-clamp-2">
            {{ row.description }}
          </p>
        </template>

        <template #cell-owner="{ row }">
          <AvatarLabel :src="row.user.photo" :name="row.user.name" class="text-gray-warm-900" />
        </template>

        <template v-if="activeTab === 'user'" #cell-actions="{ row }">
          <div class="flex gap-4">
            <Tooltip :delay-duration="700">
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="edit-01"
                  class="aspect-square p-[10px]"
                  @click="router.push({ name: 'edit-template', params: { templateId: row.id } })"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('views.templates.table.actions.edit')" />
            </Tooltip>

            <Tooltip :delay-duration="700">
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  :icon="row.enabled ? 'eye' : 'eye-off'"
                  class="aspect-square p-[10px]"
                  @click="
                    visibilityModalData = {
                      id: row.id,
                      name: row.name,
                      action: row.enabled ? 'hide' : 'show'
                    }
                  "
                />
              </TooltipTrigger>
              <TooltipContent
                :title="t(`views.templates.table.actions.${row.enabled ? 'hide' : 'show'}`)"
              />
            </Tooltip>

            <DropdownMenu>
              <DropdownMenuTrigger>
                <Button
                  hierarchy="secondary-gray"
                  icon="dots-vertical"
                  class="aspect-square p-[10px]"
                />
              </DropdownMenuTrigger>

              <DropdownMenuContent
                class="bg-white border border-gray-warm-300 rounded-lg"
                align="end"
              >
                <DropdownMenuGroup>
                  <DropdownMenuItem @click="fetchAndOpenTemplateInfoModal(row.id)">
                    <Button
                      size="sm"
                      class="mr-2 w-full justify-start"
                      hierarchy="link-gray"
                      icon="info-circle"
                      icon-size="md"
                    >
                      {{ t('views.templates.table.actions.info') }}
                    </Button>
                  </DropdownMenuItem>
                  <DropdownMenuItem>
                    <Button
                      size="sm"
                      class="mr-2 w-full justify-start"
                      hierarchy="link-gray"
                      icon="users-01"
                      icon-size="md"
                    >
                      {{ t('views.templates.table.actions.update-alloweds') }}
                    </Button>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    @click="
                      handleWithDesktopQuotaCheck(
                        () => (convertModalData = { id: row.id, name: row.name })
                      )
                    "
                  >
                    <Button
                      size="sm"
                      class="mr-2 w-full justify-start"
                      hierarchy="link-gray"
                      icon="monitor-02"
                      icon-size="md"
                    >
                      {{ t('views.templates.table.actions.template-to-desktop') }}
                    </Button>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    class="hover:bg-error-50 focus:bg-error-50"
                    @click="deleteModalData = { id: row.id, name: row.name }"
                  >
                    <Button
                      size="sm"
                      class="mr-2 w-full justify-start text-error-700"
                      hierarchy="link-gray"
                      icon="trash-04"
                      icon-size="md"
                    >
                      {{ t('views.templates.table.actions.delete') }}
                    </Button>
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </template>

        <template v-else #cell-actions="{ row }">
          <div class="flex gap-2">
            <Button
              hierarchy="secondary-gray"
              icon="copy-07"
              class="aspect-square p-[10px]"
              :disabled="templateCreationCheckIsPending"
              @click="
                handleWithTemplateQuotaCheck(() =>
                  router.push({ name: 'duplicate-template', params: { templateId: row.id } })
                )
              "
            />
          </div>
        </template>
      </TemplateDataTable>
    </div>
  </main>
</template>
