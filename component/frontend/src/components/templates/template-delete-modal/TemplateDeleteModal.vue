<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import { cn, copyToClipboard, formatHoursToHumanReadable } from '@/lib/utils'
import { toast, type ToastOptions } from '@/components/ui/toast'

import {
  deleteTemplateMutation,
  getTemplateTreeOptions,
  getRecycleBinCutoffTimeOptions,
  getUserOptions,
  getUserTemplatesQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { AvatarLabel } from '@/components/avatar-label'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem
} from '@/components/ui/context-menu'
import { DataTable } from '@/components/data-table'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Icon } from '@/components/icon'
import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { TruncatedText } from '@/components/truncated-text'

const { t, locale } = useI18n()
const router = useRouter()
const queryClient = useQueryClient()

interface Props {
  open?: boolean
  templateId: string
  templateName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const {
  data: templateTree,
  isPending: templateTreeIsPending,
  isError: templateTreeIsError,
  error: templateTreeError
} = useQuery(
  getTemplateTreeOptions({
    path: { template_id: props.templateId }
  })
)

const { data: recycleBinCutoffTime } = useQuery(getRecycleBinCutoffTimeOptions())

const { data: currentUser } = useQuery({ ...getUserOptions(), staleTime: Infinity })

const isAdmin = computed(() => currentUser.value?.role === 'admin')

const cutoffHours = computed(() => recycleBinCutoffTime.value?.recycle_bin_cutoff_time)

type CutoffState = 'temporary' | 'permanent' | 'infinite'

const cutoffState = computed<CutoffState>(() => {
  const hours = cutoffHours.value
  if (hours === 0) return 'permanent'
  if (typeof hours === 'number' && Number.isFinite(hours) && hours > 0) return 'temporary'
  return 'infinite'
})

const treeDependencies = computed(() =>
  [...(templateTree.value?.domains ?? []), ...(templateTree.value?.deployments ?? [])].filter(
    (row) => row.id !== props.templateId
  )
)

const dependencyCounts = computed(() => {
  const rows = treeDependencies.value
  return {
    total: rows.length,
    desktops: rows.filter((row) => row.kind === 'desktop').length,
    templates: rows.filter((row) => row.kind === 'template').length,
    deployments: rows.filter((row) => row.kind === 'deployment').length,
    hidden: rows.filter((row) => !row.kind).length
  }
})

const deletedTotal = computed(
  () => (templateTree.value?.domains?.length ?? 0) + (templateTree.value?.deployments?.length ?? 0)
)

const {
  mutate: deleteTemplate,
  mutateAsync: deleteTemplateAsync,
  isPending: deleteTemplateIsPending,
  isError: deleteTemplateIsError,
  error: deleteTemplateError
} = useMutation({
  ...deleteTemplateMutation(),
  onSuccess: () => {
    const count = deletedTotal.value
    const time = formatHoursToHumanReadable(cutoffHours.value ?? 0, locale.value)
    const base = 'components.templates.delete-confirmation-modal.toast'
    const state = cutoffState.value

    const title =
      state === 'permanent'
        ? t(`${base}.permanent.title`, { name: props.templateName })
        : t(`${base}.recycled.title`, { name: props.templateName })

    const description =
      state === 'temporary'
        ? t(`${base}.recycled.description`, { count, time })
        : state === 'permanent'
          ? t(`${base}.permanent.description`, { count })
          : t(`${base}.recycled-infinite.description`, { count })

    const options: ToastOptions = { description }
    if (state !== 'permanent') {
      options.actions = [
        {
          label: t(`${base}.open-recycle-bin`),
          onClick: () => router.push({ name: 'recycle-bin' })
        }
      ]
    }

    if (state === 'permanent') {
      toast.info(title, options)
    } else {
      toast.warning(title, options)
    }

    queryClient.invalidateQueries({ queryKey: getUserTemplatesQueryKey() })
    emit('close')
  }
})
</script>

<template>
  <Modal
    :open="props.open"
    level="danger"
    :size="treeDependencies.length ? '5xl' : 'lg'"
    :title="t('components.templates.delete-confirmation-modal.title', { name: props.templateName })"
    @close="emit('close')"
  >
    <div>
      <div
        v-if="templateTreeIsPending"
        class="w-full h-64 flex flex-col items-center justify-center"
      >
        <Spinner />
      </div>

      <template v-else>
        <div class="my-4 w-full flex justify-center">
          <Alert variant="warning" class="w-[min(100%,var(--spacing-256))]">
            <FeaturedIconOutline kind="outline" color="warning" />
            <AlertDescription>
              <template v-if="cutoffState === 'temporary'">{{
                t('components.templates.delete-confirmation-modal.recycle-bin.temporary', {
                  time: formatHoursToHumanReadable(cutoffHours ?? 0, locale)
                })
              }}</template>
              <template v-else-if="cutoffState === 'permanent'">{{
                t('components.templates.delete-confirmation-modal.recycle-bin.permanent')
              }}</template>
              <template v-else>{{
                t('components.templates.delete-confirmation-modal.recycle-bin.infinite')
              }}</template>
            </AlertDescription>
          </Alert>
        </div>

        <div v-if="isAdmin && templateTree?.cross_category" class="mb-4 w-full flex justify-center">
          <Alert variant="warning" class="w-[min(100%,var(--spacing-256))]">
            <FeaturedIconOutline kind="outline" color="warning" />
            <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
              t('components.templates.delete-confirmation-modal.fields.cross-category.title')
            }}</AlertTitle>
            <AlertDescription>{{
              t('components.templates.delete-confirmation-modal.fields.cross-category.description')
            }}</AlertDescription>
          </Alert>
        </div>

        <template v-if="!treeDependencies.length">
          {{ t('components.templates.delete-confirmation-modal.subtitle') }}
        </template>

        <template v-else>
          <div class="my-6 w-full flex justify-center">
            <Alert variant="destructive" class="w-[min(100%,var(--spacing-256))]">
              <FeaturedIconOutline kind="outline" color="error" />

              <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
                t('components.templates.delete-confirmation-modal.fields.dependency.alert.title')
              }}</AlertTitle>
              <AlertDescription>{{
                t(
                  `components.templates.delete-confirmation-modal.fields.dependency.alert.${templateTree.pending ? 'pending' : 'description'}`
                )
              }}</AlertDescription>
              <p class="mt-3 font-bold text-gray-warm-900">
                {{
                  t('components.templates.delete-confirmation-modal.fields.summary.total', {
                    count: dependencyCounts.total
                  })
                }}
              </p>
              <p class="text-sm text-gray-warm-600">
                {{
                  t(
                    'components.templates.delete-confirmation-modal.fields.summary.breakdown',
                    dependencyCounts
                  )
                }}
              </p>
            </Alert>
          </div>

          <DataTable
            :headers="[
              {
                name: t(
                  'components.templates.delete-confirmation-modal.fields.dependency.datatable.headers.kind'
                ),
                key: 'kind',
                width: 'max-content',
                sortable: true
              },
              {
                name: t(
                  'components.templates.delete-confirmation-modal.fields.dependency.datatable.headers.name'
                ),
                key: 'name',
                headerClass: 'w-full',
                sortable: true
              },
              {
                name: t(
                  'components.templates.delete-confirmation-modal.fields.dependency.datatable.headers.user'
                ),
                key: 'user',
                width: 'minmax(var(--spacing-48), var(--spacing-80))',
                sortable: true
              }
            ]"
            :rows="treeDependencies"
            :page-size="treeDependencies.length"
            class="mt-4"
            :loading="false"
            :is-clickable="false"
          >
            <template #cell-kind="{ row }">
              <div class="w-full h-full flex items-center justify-start gap-4 p-2">
                <ContextMenu>
                  <ContextMenuTrigger>
                    <Icon v-if="!row.kind" name="asterisk-02" />
                    <Icon v-else-if="row.kind === 'desktop'" name="monitor-02" />
                    <Icon v-else-if="row.kind === 'template'" name="colors" />
                    <Icon v-else-if="row.kind === 'deployment'" name="layout-alt-04" />
                  </ContextMenuTrigger>
                  <ContextMenuContent class="bg-white border border-gray-warm-300 rounded-lg">
                    <ContextMenuItem @click="copyToClipboard(row.id)">{{
                      t('components.templates.delete-confirmation-modal.debug-options.copy-id')
                    }}</ContextMenuItem>
                  </ContextMenuContent>
                </ContextMenu>

                <p v-if="row.kind" class="text-sm font-medium text-gray-warm-900">
                  {{ t(`domains.${row.kind}s`, 1) }}
                </p>
                <p v-else class="text-sm font-medium text-gray-warm-900 font-mono">*****</p>
              </div>
            </template>

            <template #cell-name="{ row }">
              <TruncatedText
                v-if="row.name"
                :title="row.name"
                class="text-sm font-semibold text-gray-warm-900"
              />
              <p v-else class="text-sm font-semibold text-gray-warm-900 truncate font-mono">
                *****
              </p>
            </template>

            <template #cell-user="{ row }">
              <div class="flex items-center gap-2 text-gray-warm-900">
                <template v-if="row.user">
                  <!-- TODO: send the user photo via api -->
                  <AvatarLabel :src="row.user" :name="row.user" />
                </template>
                <template v-else>
                  <Avatar>
                    <AvatarFallback><Icon name="user-03" /></AvatarFallback>
                  </Avatar>
                  <span class="text-sm font-medium text-gray-warm-900 font-mono">*****</span>
                </template>
              </div>
            </template>
          </DataTable>
        </template>
      </template>
    </div>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t('components.templates.delete-confirmation-modal.cancel')
      }}</Button>

      <!-- TODO: maybe add a confirmation checkbox -->
      <Button
        v-if="!templateTreeIsPending"
        hierarchy="destructive"
        :disabled="deleteTemplateIsPending || (templateTree && templateTree.pending)"
        @click="
          deleteTemplate({
            path: { template_id: props.templateId }
          })
        "
      >
        <Icon
          v-if="deleteTemplateIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.templates.delete-confirmation-modal.confirm') }}
      </Button>
      <Skeleton v-else class="h-full w-32" />
    </template>
  </Modal>
</template>
