<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  getDeploymentQueryKey,
  getDeploymentUserDesktopsOptions,
  getDeploymentUserDesktopsQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { deleteDesktop, deleteUserDeploymentDesktops } from '@/gen/oas/apiv4/sdk.gen'
import { DataTable } from '@/components/data-table'
import { Modal } from '@/components/modal'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toast'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { TruncatedText } from '@/components/truncated-text'
import { describeApiError } from '@/lib/api-errors'
import { desktopActionsData, desktopStatusLabel } from '@/lib/desktops'
import { formatRelativeTime } from '@/lib/utils'

interface Props {
  open?: boolean
  deploymentId: string
  userId: string
  username: string
  onSuccess?: () => void
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  onSuccess: undefined
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

const i18n = useI18n()
const { t, te, d, locale } = i18n
const queryClient = useQueryClient()

const statusLabel = (status?: string) => desktopStatusLabel(status, i18n)
const statusIcon = (status?: string) => desktopActionsData(status ?? '').text

const {
  data: userDesktops,
  isPending: desktopsIsPending,
  isError: desktopsIsError
} = useQuery(
  getDeploymentUserDesktopsOptions({
    path: { deployment_id: props.deploymentId, user_id: props.userId }
  })
)

const desktops = computed(() => userDesktops.value?.desktops ?? [])

const headers = computed(() => [
  {
    name: '',
    key: 'select',
    width: 'max-content'
  },
  {
    name: t('components.deployments.delete-desktops-modal.headers.desktop'),
    key: 'name',
    headerClass: 'w-full',
    sortable: true
  },
  {
    name: t('components.deployments.delete-desktops-modal.headers.status'),
    key: 'status',
    width: 'minmax(var(--spacing-32), var(--spacing-48))',
    sortable: true
  },
  {
    name: t('components.deployments.delete-desktops-modal.headers.last-access'),
    key: 'accessed',
    width: 'minmax(var(--spacing-40), max-content)',
    sortable: true
  },
  {
    name: t('components.deployments.delete-desktops-modal.headers.visible'),
    key: 'visible',
    width: 'max-content',
    sortable: true
  }
])

const selected = ref<string[]>([])
const errorMessage = ref<string | null>(null)
const failedCount = ref(0)

const allSelected = computed(
  () => desktops.value.length > 0 && selected.value.length === desktops.value.length
)

const masterState = computed<boolean | 'indeterminate'>(() => {
  if (allSelected.value) return true
  return selected.value.length > 0 ? 'indeterminate' : false
})

const toggle = (desktopId: string) => {
  if (deleteIsPending.value) return
  selected.value = selected.value.includes(desktopId)
    ? selected.value.filter((id) => id !== desktopId)
    : [...selected.value, desktopId]
}

const toggleAll = () => {
  if (deleteIsPending.value) return
  selected.value = allSelected.value ? [] : desktops.value.map((desktop) => desktop.id)
}

const { mutate: deleteSelected, isPending: deleteIsPending } = useMutation({
  mutationFn: async () => {
    failedCount.value = 0

    if (allSelected.value) {
      await deleteUserDeploymentDesktops({
        path: { deployment_id: props.deploymentId, user_id: props.userId },
        throwOnError: true
      })
      return
    }

    const results = await Promise.allSettled(
      selected.value.map((desktopId) =>
        deleteDesktop({
          path: { desktop_id: desktopId },
          query: { permanent: true },
          throwOnError: true
        })
      )
    )
    const rejected = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected')
    if (rejected.length > 0) {
      failedCount.value = rejected.length
      throw rejected[0].reason
    }
  },
  onSuccess: () => {
    toast.success(t('components.deployments.delete-desktops-modal.success'))
    handleClose()
    if (props.onSuccess) props.onSuccess()
  },
  onError: (error) => {
    errorMessage.value =
      failedCount.value > 1
        ? t('components.deployments.delete-desktops-modal.error-partial', {
            n: failedCount.value
          })
        : describeApiError(error, { t, te }, 'delete-desktop')
  },
  onSettled: () => {
    selected.value = []
    queryClient.invalidateQueries({
      queryKey: getDeploymentQueryKey({ path: { deployment_id: props.deploymentId } })
    })
    queryClient.invalidateQueries({
      queryKey: getDeploymentUserDesktopsQueryKey({
        path: { deployment_id: props.deploymentId, user_id: props.userId }
      })
    })
  }
})

const handleClose = () => {
  selected.value = []
  errorMessage.value = null
  failedCount.value = 0
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    size="4xl"
    :close-on-backdrop-click="!deleteIsPending"
    :title="t('components.deployments.delete-desktops-modal.title', { name: props.username })"
    :description="t('components.deployments.delete-desktops-modal.description')"
    @close="handleClose"
  >
    <div class="flex flex-col gap-4 pb-2">
      <Alert v-if="errorMessage" variant="destructive">
        <AlertDescription>{{ errorMessage }}</AlertDescription>
      </Alert>

      <div v-if="desktopsIsPending" class="flex flex-col gap-2">
        <Skeleton v-for="index in 2" :key="index" class="h-12 w-full" />
      </div>

      <Alert v-else-if="desktopsIsError" variant="destructive">
        <AlertDescription>{{
          t('components.deployments.delete-desktops-modal.error-loading')
        }}</AlertDescription>
      </Alert>

      <DataTable
        v-else
        :headers="headers"
        :rows="desktops"
        :page-size="desktops.length || 1"
        :is-clickable="true"
        cell-class="h-14"
        @row-click="(row) => toggle(row.id as string)"
      >
        <template #head-select>
          <Checkbox
            :model-value="masterState"
            :indeterminate="masterState === 'indeterminate'"
            :disabled="deleteIsPending || desktops.length === 0"
            :aria-label="t('components.deployments.delete-desktops-modal.select-all')"
            data-slot="select-all"
            size="md"
            class="bg-base-white"
            @update:model-value="toggleAll"
          />
        </template>

        <template #cell-select="{ row }">
          <span class="flex items-center" @click.stop>
            <Checkbox
              :model-value="selected.includes(row.id as string)"
              :disabled="deleteIsPending"
              :aria-label="row.name as string"
              size="md"
              class="bg-base-white"
              @update:model-value="toggle(row.id as string)"
            />
          </span>
        </template>

        <template #cell-name="{ row }">
          <TruncatedText
            :title="row.name as string"
            class="text-sm font-semibold text-gray-warm-900"
          />
        </template>

        <template #cell-status="{ row }">
          <div class="flex items-center gap-2 text-sm font-medium text-gray-warm-700">
            <Icon
              v-if="statusIcon(row.status as string)"
              :name="statusIcon(row.status as string)!.icon"
              size="md"
              class="shrink-0"
              :class="statusIcon(row.status as string)!.iconClass"
              :stroke-color="statusIcon(row.status as string)!.iconColor"
            />
            {{ statusLabel(row.status as string) }}
          </div>
        </template>

        <template #cell-accessed="{ row }">
          <Tooltip v-if="row.accessed">
            <TooltipTrigger as-child>
              <span class="text-sm text-gray-warm-700">
                {{
                  d((row.accessed as number) * 1000, { dateStyle: 'short' }) +
                  ', ' +
                  d((row.accessed as number) * 1000, { timeStyle: 'medium' })
                }}
              </span>
            </TooltipTrigger>
            <TooltipContent :title="formatRelativeTime(row.accessed as number, locale)" />
          </Tooltip>
          <span v-else class="text-sm text-gray-warm-500">&mdash;</span>
        </template>

        <template #cell-visible="{ row }">
          <Tooltip v-if="row.visible !== null && row.visible !== undefined">
            <TooltipTrigger as-child>
              <Icon
                :name="row.visible ? 'eye' : 'eye-off'"
                size="md"
                :stroke-color="row.visible ? 'gray-warm-700' : 'gray-warm-400'"
                :aria-label="
                  t(
                    row.visible
                      ? 'views.deployments.visibility.visible'
                      : 'views.deployments.visibility.hidden'
                  )
                "
              />
            </TooltipTrigger>
            <TooltipContent
              :title="
                t(
                  row.visible
                    ? 'views.deployments.visibility.visible'
                    : 'views.deployments.visibility.hidden'
                )
              "
            />
          </Tooltip>
          <span v-else class="text-sm text-gray-warm-500">&mdash;</span>
        </template>

        <template #empty>
          {{ t('components.deployments.delete-desktops-modal.empty') }}
        </template>
      </DataTable>
    </div>

    <template #footer>
      <Button hierarchy="link-gray" :disabled="deleteIsPending" @click="handleClose">
        {{ t('components.deployments.delete-desktops-modal.cancel') }}
      </Button>
      <Button
        hierarchy="destructive"
        :disabled="deleteIsPending || selected.length === 0"
        @click="deleteSelected()"
      >
        <Icon
          v-if="deleteIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.deployments.delete-desktops-modal.confirm', selected.length) }}
      </Button>
    </template>
  </Modal>
</template>
