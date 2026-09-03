<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  getTemplateDetailsOptions,
  getTemplateDetailsQueryKey,
  getTemplateInfoQueryKey,
  updateTemplateMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { FormHeader } from '@/components/form-header'
import { describeApiError } from '@/lib/api-errors'
import DomainConfigurationPanel from '@/components/domain/DomainConfigurationPanel.vue'
import {
  toDomainHardware,
  toGuestProperties,
  toImageInput,
  toReservables
} from '@/lib/domainPayload'

const route = useRoute()
const router = useRouter()
const { t, te } = useI18n()
const queryClient = useQueryClient()

const templateId = computed(() => route.params.templateId as string)

const { data: templateDetails, isPending: templateDetailsIsPending } = useQuery({
  ...getTemplateDetailsOptions({
    path: { template_id: templateId.value }
  }),
  staleTime: 0,
  refetchOnMount: 'always'
})

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)
const panelRef = ref<InstanceType<typeof DomainConfigurationPanel> | null>(null)
const areFormsValid = computed(() => panelRef.value?.areFormsValid ?? false)
const isTouched = computed(() => panelRef.value?.isDirty ?? false)

const submitError = ref<string | null>(null)

const { mutate: submitEdit, isPending: submitPending } = useMutation({
  ...updateTemplateMutation(),
  onSuccess: () => {
    queryClient.removeQueries({
      queryKey: getTemplateDetailsQueryKey({ path: { template_id: templateId.value } }),
      exact: true
    })
    queryClient.removeQueries({
      queryKey: getTemplateInfoQueryKey({ path: { template_id: templateId.value } }),
      exact: true
    })
    formHeaderRef.value?.allowLeave()
    router.push({ name: 'templates' })
  },
  onError: (error) => {
    submitError.value = describeApiError(error, { t, te }, 'edit-template')
  }
})

const handleSubmit = () => {
  if (!areFormsValid.value || !panelRef.value) return
  submitError.value = null

  const data = panelRef.value.getFormData()

  // No bastion_target: TemplateEditRequest has no such field.
  submitEdit({
    path: { template_id: templateId.value },
    body: {
      name: data.name,
      description: data.description,
      image: toImageInput(data.image, data.imageFile),
      guest_properties: toGuestProperties(data.access),
      hardware: toDomainHardware(data.hardware),
      reservables: toReservables(data.hardware)
    }
  })
}
</script>

<template>
  <FormHeader
    ref="formHeaderRef"
    :cancel-to="{ name: 'templates' }"
    :cancel-label="t('components.form-header.cancel-edit')"
    :confirm-cancel="isTouched"
    :next-label="t('views.edit-template.header.save')"
    :next-disabled="!areFormsValid || templateDetailsIsPending"
    :next-pending="submitPending"
    @next="handleSubmit"
  />

  <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
    <Alert v-if="submitError" variant="destructive" class="max-w-256 w-full mx-auto">
      <FeaturedIconOutline kind="outline" color="error" />
      <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
        t('views.edit-template.errors.title')
      }}</AlertTitle>
      <AlertDescription>{{ submitError }}</AlertDescription>
    </Alert>

    <DomainConfigurationPanel
      ref="panelRef"
      :template-id="templateId"
      :loading="templateDetailsIsPending"
      :info="templateDetails"
      entity="templates"
      preview="template-row"
      :image="templateDetails?.image"
      :image-domain-id="templateId"
      :image-persist-on-save="false"
      :image-allow-upload="false"
      always-show-configuration
      context="edit-template"
    />
  </main>
</template>
