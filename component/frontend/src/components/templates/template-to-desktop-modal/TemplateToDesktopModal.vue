<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'

import { cn, copyToClipboard } from '@/lib/utils'

import {
  getTemplateTreeApiV4ItemTemplateTemplateIdGetTreeGetOptions,
  convertTemplateToDesktopApiV4ItemTemplateTemplateIdConvertToDesktopPostMutation
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
import { InputField } from '@/components/input-field'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldTitle
} from '@/components/ui/field'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

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
  getTemplateTreeApiV4ItemTemplateTemplateIdGetTreeGetOptions({
    path: { template_id: props.templateId }
  })
)

const filteredDomains = computed(() => {
  if (!templateTree.value) return []

  const dependencies = [
    ...(templateTree.value.domains ?? []),
    ...(templateTree.value.deployments ?? [])
  ]

  // remove the current template from the dependencies
  return dependencies.filter((domain) => {
    return domain.id !== props.templateId
  })
})

const {
  mutate: convertTemplate,
  mutateAsync: convertTemplateAsync,
  isPending: convertTemplateIsPending,
  isError: convertTemplateIsError,
  error: convertTemplateError
} = useMutation({
  ...convertTemplateToDesktopApiV4ItemTemplateTemplateIdConvertToDesktopPostMutation(),
  onSuccess: () => {
    emit('close')
  }
})

const convertBlocked = computed(() => {
  return (
    convertTemplateIsPending.value ||
    (templateTree.value && (templateTree.value.pending || templateTree.value.is_duplicated)) ||
    filteredDomains.value.length > 0 ||
    templateTreeIsError.value
  )
})

const convertBlockedReason = computed(() => {
  if (templateTree.value && templateTree.value.is_duplicated) {
    return 'duplicated'
  }
  if (templateTree.value && templateTree.value.pending) {
    return 'pending'
  }
  if (filteredDomains.value.length > 0) {
    return 'dependencies'
  }
  if (templateTreeIsError.value) {
    return 'error'
  }
  return null
})

const formSchema = z.object({
  name: z.string().min(1, t('components.form.validation.required'))
})

const form = useForm({
  defaultValues: {
    name: props.templateName
  },
  validators: {
    onBlur: formSchema
  },
  onSubmit: async ({ value }) => {
    await convertTemplateAsync({
      path: { template_id: props.templateId },
      body: {
        name: value.name
      }
    })
  }
})

function isInvalid(field) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}
</script>

<template>
  <Modal
    :open="props.open"
    level="danger"
    :size="filteredDomains.length > 0 ? '5xl' : 'lg'"
    :title="t('components.templates.convert-to-desktop-modal.title', { name: props.templateName })"
    class="pt-[24px]"
    @close="emit('close')"
  >
    <div>
      <div
        v-if="templateTreeIsPending"
        class="w-full h-64 flex flex-col items-center justify-center"
      >
        <Spinner />
      </div>

      <template v-else-if="convertBlocked">
        <div v-if="convertBlocked && convertBlockedReason" class="my-6 w-full flex justify-center">
          <Alert variant="destructive" class="max-w-256 w-full">
            <FeaturedIconOutline kind="outline" color="error" />

            <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
              t('components.templates.convert-to-desktop-modal.alert.title')
            }}</AlertTitle>
            <AlertDescription>{{
              t(
                `components.templates.convert-to-desktop-modal.alert.description.${convertBlockedReason}`
              )
            }}</AlertDescription>
          </Alert>
        </div>

        <DataTable
          v-if="filteredDomains.length > 0"
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
          :rows="filteredDomains"
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

      <div v-else class="w-full flex flex-col items-center justify-center">
        <form class="flex flex-col gap-5 max-w-256 w-full" @submit.prevent="form.handleSubmit">
          <form.Field v-slot="{ field }" name="name">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">{{
                t('components.templates.convert-to-desktop-modal.form.name.label')
              }}</FieldLabel>
              <InputField
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                autocomplete="off"
                type="text"
                @blur="field.handleBlur"
                @input="field.handleChange($event.target.value)"
              />
              <FieldDescription>{{
                t('components.templates.convert-to-desktop-modal.form.name.description')
              }}</FieldDescription>
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </form.Field>
        </form>
      </div>
    </div>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t('components.templates.convert-to-desktop-modal.cancel')
      }}</Button>

      <Button
        v-if="!templateTreeIsPending"
        type="submit"
        hierarchy="primary"
        :disabled="convertBlocked"
        @click="form.handleSubmit"
      >
        <Icon
          v-if="convertTemplateIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.templates.convert-to-desktop-modal.confirm') }}
      </Button>
      <Skeleton v-else class="h-full w-32" />
    </template>
  </Modal>
</template>
