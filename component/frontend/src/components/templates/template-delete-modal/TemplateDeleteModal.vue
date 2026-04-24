<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'

import { cn, copyToClipboard } from '@/lib/utils'

import {
  deleteTemplateMutation,
  getTemplateTreeOptions
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

const { t, d } = useI18n()

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

const {
  mutate: deleteTemplate,
  mutateAsync: deleteTemplateAsync,
  isPending: deleteTemplateIsPending,
  isError: deleteTemplateIsError,
  error: deleteTemplateError
} = useMutation({
  ...deleteTemplateMutation(),
  onSuccess: () => {
    emit('close')
  }
})

const treeDependencies = computed(() => [
  ...(templateTree.value?.domains ?? []),
  ...(templateTree.value?.deployments ?? [])
])
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

      <template v-else-if="!treeDependencies.length">
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
            <p v-if="row.name" class="text-sm font-semibold text-gray-warm-900 truncate">
              {{ row.name }}
            </p>
            <p v-else class="text-sm font-semibold text-gray-warm-900 truncate font-mono">*****</p>
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
