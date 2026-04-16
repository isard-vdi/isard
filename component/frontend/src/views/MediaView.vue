<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  getUserMediaApiV4ItemsMediaGetOptions,
  getUserSharedMediaApiV4ItemsMediaGetSharedGetOptions,
  startMediaDownloadApiV4ItemMediaMediaIdDownloadPutMutation,
  abortMediaDownloadApiV4ItemMediaMediaIdAbortPutMutation,
  deleteMediaApiV4ItemMediaMediaIdDeleteMutation,
  checkQuotaNewMediaApiV4QuotaMediaNewGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { MediaStatusEnum, type ErrorResponse } from '@/gen/oas/apiv4'
import DataTable from '@/components/data-table/DataTable.vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { computed, ref } from 'vue'
import InputField from '@/components/input-field/InputField.vue'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import Skeleton from '@/components/ui/skeleton/Skeleton.vue'
import Progress from '@/components/ui/progress/Progress.vue'
import Badge from '@/components/badge/Badge.vue'
import AvatarLabel from '@/components/avatar-label/AvatarLabel.vue'
import Icon from '@/components/icon/Icon.vue'
import templatesEmptyImg from '@/assets/img/templates-empty.svg'
import { type MediaItemResponse, type UserSharedMedia } from '@/gen/oas/apiv4'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toggleVariants } from '@/components/ui/toggle'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { useMutation } from '@tanstack/vue-query'
import NewMediaModal from '@/components/media/NewMediaModal.vue'
import { AlertModal, QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'

const { t, d, te } = useI18n()
const router = useRouter()

const goToNewFromMedia = (mediaId: string) => {
  router.push({ name: 'new-from-media', params: { mediaId } })
}
const queryClient = useQueryClient()

const activeTab = ref<'user' | 'shared'>('user')
const showNewMediaModal = ref(false)
const showQuotaExceededModal = ref(false)
const checkQuotaIsPending = ref(false)

const openNewMediaModal = async () => {
  checkQuotaIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewMediaApiV4QuotaMediaNewGetOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    checkQuotaIsPending.value = false
    showNewMediaModal.value = true
  } catch {
    checkQuotaIsPending.value = false
    showQuotaExceededModal.value = true
  }
}

// Queries
const {
  isPending: userMediaIsPending,
  isError: userMediaIsError,
  error: userMediaError,
  data: userMedia
} = useQuery(getUserMediaApiV4ItemsMediaGetOptions())

const {
  isFetching: sharedMediaIsFetching,
  isError: sharedMediaIsError,
  error: sharedMediaError,
  data: sharedMedia,
  refetch: fetchSharedMedia
} = useQuery({
  ...getUserSharedMediaApiV4ItemsMediaGetSharedGetOptions(),
  enabled: false
})

const actionErrorModal = ref<{ messageKey: string; detail: string } | null>(null)

const formatErrorDetail = (error: unknown): string => {
  const err = error as ErrorResponse | undefined
  return err?.description || err?.description_code || t('views.media.action-error-modal.fallback')
}

const { mutate: downloadMedia } = useMutation({
  ...startMediaDownloadApiV4ItemMediaMediaIdDownloadPutMutation(),
  onError: (error) => {
    actionErrorModal.value = {
      messageKey: 'views.media.action-error-modal.download',
      detail: formatErrorDetail(error)
    }
  }
})

const { mutate: abortDownload } = useMutation({
  ...abortMediaDownloadApiV4ItemMediaMediaIdAbortPutMutation(),
  onError: (error) => {
    actionErrorModal.value = {
      messageKey: 'views.media.action-error-modal.abort',
      detail: formatErrorDetail(error)
    }
  }
})

const { mutate: deleteMedia, isPending: deleteMediaIsPending } = useMutation({
  ...deleteMediaApiV4ItemMediaMediaIdDeleteMutation(),
  onError: (error) => {
    actionErrorModal.value = {
      messageKey: 'views.media.action-error-modal.delete',
      detail: formatErrorDetail(error)
    }
  },
  onSettled: (_data, _error) => {
    closeDeleteModal()
  }
})

const getStatusConfig = (status: MediaStatusEnum) => {
  switch (status) {
    case MediaStatusEnum.DOWNLOADED:
      return {
        icon: 'dot',
        color: 'green'
      }
    case MediaStatusEnum.DOWNLOADING:
      return {
        icon: 'dot',
        color: 'blue'
      }
    case MediaStatusEnum.DOWNLOAD_STARTING:
      return {
        icon: 'dot',
        color: 'blue'
      }
    case MediaStatusEnum.DOWNLOAD_ABORTING:
      return {
        icon: 'dot',
        color: 'blue'
      }
    case MediaStatusEnum.RESET_DOWNLOADING:
      return {
        icon: 'dot',
        color: 'blue'
      }
    case MediaStatusEnum.DOWNLOAD:
      return {
        icon: 'dot',
        color: 'gray'
      }
    case MediaStatusEnum.DOWNLOAD_FAILED:
      return {
        icon: 'alert-circle',
        color: 'red'
      }
    case MediaStatusEnum.DOWNLOAD_FAILED_INVALID_FORMAT:
      return {
        icon: 'alert-triangle',
        color: 'red'
      }
    case MediaStatusEnum.DELETING:
      return {
        icon: 'alert-circle',
        color: 'lightyellow'
      }
    case MediaStatusEnum.MAINTENANCE:
      return {
        icon: 'alert-circle',
        color: 'lightyellow'
      }
    default:
      return {
        icon: 'alert-circle',
        color: 'red'
      }
  }
}

const mediaIconName = (kind: string) => (kind === 'iso' ? 'disc-02' : 'save-02')

const currentMedia = computed(() => {
  return activeTab.value === 'user'
    ? (userMedia.value?.media ?? [])
    : (sharedMedia.value?.media ?? [])
})

const visibleMedia = computed(() => {
  return currentMedia.value.filter(isMediaVisible)
})

const filteredMedia = computed(() => {
  return visibleMedia.value.map((item) => {
    const statusConfig = getStatusConfig(item.status)
    const size = item.progress?.total ?? '0B'
    const statusKey = (item.status ?? '').toLowerCase()
    const statusPath = `views.media.status.${statusKey}`
    const statusLabel =
      statusKey && te(statusPath) ? t(statusPath) : t('views.media.status.unknown')

    return {
      ...item,
      size,
      statusLabel,
      statusConfig
    }
  })
})

const inputSearch = ref<string>('')

// Return true if media name or description matches search input
const isMediaVisible = (media: MediaItemResponse | UserSharedMedia) => {
  const matchesSearch =
    inputSearch.value.toLowerCase() === '' ||
    media.name.toLowerCase().includes(inputSearch.value.toLocaleLowerCase()) ||
    media.description?.toLowerCase().includes(inputSearch.value.toLocaleLowerCase())

  return matchesSearch
}

const userHeaders = computed(() => [
  {
    key: 'name',
    name: t('views.media.data-table.headers.name'),
    sortable: true
  },
  {
    key: 'description',
    name: t('views.media.data-table.headers.description'),
    sortable: true
  },
  {
    key: 'size',
    name: t('views.media.data-table.headers.size'),
    sortable: true,
    width: '150px'
  },
  {
    key: 'kind',
    name: t('views.media.data-table.headers.kind'),
    sortable: true,
    width: '150px'
  },
  {
    key: 'accessed',
    name: t('views.media.data-table.headers.date'),
    sortable: true,
    width: 'max-content'
  },
  {
    key: 'status',
    name: t('views.media.data-table.headers.status'),
    sortable: true,
    width: '250px'
  },
  {
    key: 'actions',
    name: '',
    sortable: false,
    width: 'max-content'
  }
])

const sharedHeaders = computed(() => [
  {
    key: 'name',
    name: t('views.media.data-table.headers.name'),
    sortable: true
  },
  {
    key: 'description',
    name: t('views.media.data-table.headers.description'),
    sortable: true
  },
  {
    key: 'kind',
    name: t('views.media.data-table.headers.kind'),
    sortable: true,
    width: '170px'
  },
  {
    key: 'accessed',
    name: t('views.media.data-table.headers.date'),
    sortable: true,
    width: 'minmax(150px, max-content)'
  },
  {
    key: 'user',
    name: t('views.media.data-table.headers.user'),
    sortable: true,
    width: 'minmax(200px, max-content)'
  },
  {
    key: 'category_name',
    name: t('views.media.data-table.headers.category'),
    sortable: true,
    width: 'minmax(100px, max-content)'
  },
  {
    key: 'group_name',
    name: t('views.media.data-table.headers.group'),
    sortable: true,
    width: 'minmax(100px, max-content)'
  },
  {
    key: 'status',
    name: t('views.media.data-table.headers.status'),
    sortable: true,
    width: '200px'
  }
])

const headers = computed(() =>
  activeTab.value === 'user' ? userHeaders.value : sharedHeaders.value
)

const emptyMessage = (input: string) => {
  return input.length > 0
    ? t('components.empty-search.title')
    : t('components.empty.title', { kind: t('domains.media', 0) })
}

const handleSharedTabClick = () => {
  if (!sharedMedia.value) {
    fetchSharedMedia()
  }
}

const handleDownloadMedia = (mediaId: string) => {
  downloadMedia({ path: { media_id: mediaId } })
}

const handleAbortClick = (mediaId: string) => {
  abortDownload({ path: { media_id: mediaId } })
}

const deleteModalMediaData = ref<{
  id: string
  name: string
} | null>(null)

const handleDeleteClick = (mediaId: string, mediaName: string) => {
  deleteModalMediaData.value = {
    id: mediaId,
    name: mediaName
  }
}

const closeDeleteModal = () => {
  deleteModalMediaData.value = null
}
</script>

<template>
  <main class="flex flex-col gap-6 p-4 w-full max-w-420 m-auto">
    <div v-if="userMediaIsError || sharedMediaIsError" class="text-center text-error-500">
      <pre v-if="userMediaError">{{ userMediaError }}</pre>
      <pre v-if="sharedMediaError">{{ sharedMediaError }}</pre>
    </div>
    <div class="flex flex-row w-full gap-4 items-center">
      <Tabs v-model="activeTab" class="mr-auto">
        <TabsList class="flex w-fit gap-[--spacing(1)] rounded-md">
          <TabsTrigger
            value="user"
            :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
          >
            <Icon name="user-03" stroke-color="currentColor" />
            {{ t('components.media.media-type.owned') }}
          </TabsTrigger>
          <TabsTrigger
            value="shared"
            :class="toggleVariants({ variant: 'desktops-all', size: 'default' })"
            @click="handleSharedTabClick"
          >
            <Icon name="share-06" stroke-color="currentColor" />
            {{ t('components.media.media-type.shared') }}
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <Button icon="plus" :disabled="checkQuotaIsPending" @click="openNewMediaModal">
        {{ t('components.media.new.button') }}
      </Button>
    </div>
    <InputField
      v-model="inputSearch"
      :placeholder="t('views.media.filters.search.placeholder')"
      icon="search-lg"
      class="h-min w-full max-w-120 mr-auto"
    />

    <div v-if="userMediaIsPending || sharedMediaIsFetching" class="flex flex-col gap-4 mt-8">
      <div v-for="n in 4" :key="'skeleton-row-' + n">
        <Skeleton class="h-16 w-full rounded-r-2xl" />
      </div>
    </div>

    <template v-else-if="filteredMedia.length > 0">
      <DataTable :headers="headers" :rows="filteredMedia" :is-clickable="false" cell-class="h-19">
        <template #cell-name="{ row }">
          <div class="flex items-center gap-2 text-sm font-semibold">
            <Icon :name="mediaIconName(row.kind)" stroke-color="currentColor" />
            {{ row.name }}
          </div>
        </template>
        <template #cell-description="{ row }">
          <div class="text-xs font-medium">{{ row.description }}</div>
        </template>
        <template #cell-kind="{ row }">
          <div class="text-sm font-normal">{{ row.kind }}</div>
        </template>
        <template #cell-size="{ row }">
          <div class="text-sm font-medium">{{ row.size }}</div>
        </template>
        <template #cell-status="{ row }">
          <div v-if="row.status === MediaStatusEnum.DOWNLOADING && activeTab === 'user'">
            <div class="text-end text-xs mb-0.5">{{ row.progress.total_percent ?? 0 }}%</div>
            <Progress
              :class="'h-2 text-info-400 w-50'"
              :model-value="row.progress.total_percent ?? 0"
            />
          </div>
          <template
            v-else-if="row.status === MediaStatusEnum.DOWNLOADING && activeTab === 'shared'"
          >
            <Tooltip>
              <TooltipTrigger as-child>
                <Badge
                  :color="row.statusConfig.color"
                  :class="'gap-1.5'"
                  :content="row.statusLabel"
                  shape="square"
                  size="sm"
                  :icon="row.statusConfig.icon"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('views.media.tooltip.unavailable')" side="top" />
            </Tooltip>
          </template>
          <template v-else-if="row.status === MediaStatusEnum.DOWNLOAD_FAILED_INVALID_FORMAT">
            <Tooltip>
              <TooltipTrigger as-child>
                <Badge
                  :color="row.statusConfig.color"
                  :class="'gap-1.5'"
                  :content="row.statusLabel"
                  shape="square"
                  size="sm"
                  :icon="row.statusConfig.icon"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('views.media.tooltip.invalid-format')" side="top" />
            </Tooltip>
          </template>
          <template v-else>
            <Badge
              :color="row.statusConfig.color"
              :class="'gap-1.5'"
              :content="row.statusLabel"
              shape="square"
              size="sm"
              :icon="row.statusConfig.icon"
            />
          </template>
        </template>
        <template #cell-user="{ row }">
          <div>
            <AvatarLabel :src="row.user.photo" :name="row.user.name" class="text-gray-warm-800" />
          </div>
        </template>
        <template #cell-accessed="{ row }">
          <div class="text-sm font-normal">
            {{ d(row.accessed * 1000, { dateStyle: 'short' }) }}
          </div>
        </template>
        <template #cell-category_name="{ row }">
          <div class="text-sm font-normal">{{ row.category_name }}</div>
        </template>
        <template #cell-group_name="{ row }">
          <div class="text-sm font-normal">{{ row.group_name }}</div>
        </template>
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end w-full h-full gap-6">
            <Tooltip v-if="row.status === MediaStatusEnum.DOWNLOADING">
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="stop"
                  class="aspect-square p-[10px]"
                  @click="handleAbortClick(row.id)"
                ></Button>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                :title="t('views.media.tooltip.buttons.stop-download.title')"
              />
            </Tooltip>
            <Tooltip v-if="row.status === MediaStatusEnum.DOWNLOAD_FAILED">
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="refresh-cw-01"
                  class="aspect-square p-[10px]"
                  @click="handleDownloadMedia(row.id)"
                ></Button>
              </TooltipTrigger>
              <TooltipContent
                :side="'top'"
                :title="t('views.media.tooltip.buttons.download.title')"
              />
            </Tooltip>
            <Tooltip v-if="row.status === MediaStatusEnum.DOWNLOADED">
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="plus"
                  class="aspect-square p-[10px]"
                  @click="goToNewFromMedia(row.id)"
                ></Button>
              </TooltipTrigger>
              <TooltipContent :side="'top'" :title="t('views.media.actions.new-from-media')" />
            </Tooltip>
            <Tooltip
              v-if="
                row.status === MediaStatusEnum.DOWNLOADED ||
                row.status === MediaStatusEnum.DOWNLOAD_FAILED
              "
            >
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="trash-04"
                  class="aspect-square p-[10px]"
                  @click="handleDeleteClick(row.id, row.name)"
                ></Button>
              </TooltipTrigger>
              <TooltipContent
                :side="'top'"
                :title="t('views.media.tooltip.buttons.delete.title')"
              />
            </Tooltip>
          </div>
        </template>
      </DataTable>
    </template>
    <template v-else>
      <Empty class="md:flex-row-reverse mt-16">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none">
            <img :src="templatesEmptyImg" />
          </EmptyMedia>
        </EmptyHeader>
        <div class="flex flex-col items-start text-left gap-4">
          <EmptyTitle class="text-[60px] leading-18 font-bold text-gray-warm-950">
            {{ emptyMessage(inputSearch) }}
          </EmptyTitle>
        </div>
      </Empty>
    </template>
    <!-- Delete Modal -->
    <AlertModal
      :open="deleteModalMediaData !== null"
      level="danger"
      :title="
        t('views.media.delete-confirmation-modal.title', {
          name: deleteModalMediaData?.name
        })
      "
      :description="t('views.media.delete-confirmation-modal.subtitle')"
      @close="closeDeleteModal"
    >
      <template #footer>
        <Button hierarchy="link-gray" @click="closeDeleteModal()">{{
          t('views.media.delete-confirmation-modal.cancel')
        }}</Button>

        <Button
          hierarchy="destructive"
          :disabled="deleteMediaIsPending"
          @click="deleteMedia({ path: { media_id: deleteModalMediaData!.id } })"
        >
          <Icon
            v-if="deleteMediaIsPending"
            class="motion-safe:animate-[spin_2s_linear_infinite]"
            name="loading-02"
            stroke-color="currentColor"
          />
          {{ t('views.media.delete-confirmation-modal.confirm') }}
        </Button>
      </template>
    </AlertModal>
  </main>

  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="showQuotaExceededModal"
    :title="t('components.media.quota-exceeded-modal.title')"
    :description="t('components.media.quota-exceeded-modal.description')"
    :cancel-label="t('components.media.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'media' }"
    @close="showQuotaExceededModal = false"
  />
  <NewMediaModal :open="showNewMediaModal" @close="showNewMediaModal = false" />

  <!-- Action Error Modal -->
  <AlertModal
    :open="actionErrorModal !== null"
    level="danger"
    :title="t('views.media.action-error-modal.title')"
    :description="
      actionErrorModal ? `${t(actionErrorModal.messageKey)}\n\n${actionErrorModal.detail}` : ''
    "
    @close="actionErrorModal = null"
  >
    <template #footer>
      <Button hierarchy="primary" @click="actionErrorModal = null">{{
        t('views.media.action-error-modal.close')
      }}</Button>
    </template>
  </AlertModal>
</template>
