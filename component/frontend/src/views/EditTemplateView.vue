<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { z } from 'zod'
import { useForm } from '@tanstack/vue-form'

import {
  getTemplateInfoOptions,
  updateTemplateMutation,
  getUserTemplatesQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import router from '@/router'

const { t } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()

const templateId = computed(() => route.params.templateId as string)

const {
  isPending: templateLoading,
  isError: templateLoadError,
  data: templateData
} = useQuery({
  ...getTemplateInfoOptions({
    path: { template_id: templateId.value }
  }),
  enabled: computed(() => !!templateId.value)
})

const templateInfoFormSchema = z.object({
  name: z.string().min(4).max(50),
  description: z.string().max(255).optional()
})

const defaultValues = reactive({
  name: '',
  description: ''
})

const templateInfoForm = useForm({
  defaultValues,
  validators: {
    onChange: templateInfoFormSchema
  }
})

const infoValid = templateInfoForm.useStore((state) => state.isValid)

watch(
  templateData,
  (data) => {
    if (!data) return
    templateInfoForm.setFieldValue('name', data.name)
    templateInfoForm.setFieldValue('description', data.description || '')
  },
  { immediate: true }
)

const accessFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
} | null>(null)
const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  limitedFields: Record<string, unknown> | null
  addInterface: (ifaceId: string) => void
  removeInterface: (ifaceId: string) => void
  interfaces: { value: string[] }
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces?.value ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  hardwareFormRef.value?.addInterface(ifaceId)
}
const hardwareFormIsValid = computed(() => hardwareFormRef.value?.isValid ?? true)
const accessFormIsValid = computed(() => accessFormRef.value?.isValid ?? true)

const areFormsValid = computed(
  () => infoValid.value && hardwareFormIsValid.value && accessFormIsValid.value
)

const submitError = ref<string | null>(null)

const { mutate: submitEdit, isPending: submitPending } = useMutation({
  ...updateTemplateMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: getUserTemplatesQueryKey() })
    router.push({ name: 'templates' })
  },
  onError: (error) => {
    submitError.value = 'description_code' in error ? error.description_code : 'submit'
  }
})

const handleSubmit = () => {
  if (!areFormsValid.value) return
  submitError.value = null

  const accessSettings = accessFormRef.value?.getFormData() as Record<string, unknown> | undefined
  const hardwareSettings = hardwareFormRef.value?.getFormData() as
    | Record<string, unknown>
    | undefined

  submitEdit({
    path: { template_id: templateId.value },
    body: {
      name: templateInfoForm.getFieldValue('name'),
      description: templateInfoForm.getFieldValue('description'),
      guest_properties: {
        credentials: accessSettings?.credentials,
        fullscreen: accessSettings?.fullscreen,
        viewers: accessSettings?.viewers
      },
      hardware: {
        vcpus: hardwareSettings?.vcpus,
        memory: hardwareSettings?.memory,
        disk_bus: hardwareSettings?.diskBus,
        videos: [hardwareSettings?.videos],
        boot_order: [hardwareSettings?.bootOrder],
        interfaces: hardwareSettings?.interfaces,
        isos: hardwareSettings?.isos,
        floppies: hardwareSettings?.floppies
      },
      reservables: hardwareSettings?.reservables as { vgpus?: string[] } | undefined
    }
  })
}
</script>

<template>
  <header class="flex flex-col md:flex-row items-center max-w-480 w-full mx-auto mb-8 gap-4">
    <div class="flex flex-row items-center gap-4 w-full">
      <Button
        :as="RouterLink"
        :to="{ name: 'templates' }"
        hierarchy="link-color"
        icon="arrow-left"
        class="pb-6 pt-0 pl-0"
      >
        {{ t('views.edit-template.header.cancel') }}
      </Button>
    </div>
    <div class="flex flex-row items-center justify-end gap-4 w-full">
      <Button class="min-w-32" :disabled="!areFormsValid || submitPending" @click="handleSubmit">
        {{ t('views.edit-template.header.save') }}
      </Button>
    </div>
  </header>

  <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
    <Alert v-if="templateLoadError" variant="destructive">
      <AlertTitle>{{ t('views.edit-template.errors.load') }}</AlertTitle>
    </Alert>
    <Alert v-if="submitError" variant="destructive">
      <AlertTitle>{{ t('views.edit-template.errors.submit') }}</AlertTitle>
      <AlertDescription>{{ submitError }}</AlertDescription>
    </Alert>

    <template v-if="templateLoading">
      <Skeleton class="w-full h-40" />
      <Skeleton class="w-full h-40" />
    </template>
    <template v-else-if="templateData">
      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-template.sections.info.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-template.sections.info.description') }}
        </p>
        <div class="flex flex-col gap-3">
          <templateInfoForm.Field v-slot="{ field }" name="name">
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              maxlength="50"
              @update:model-value="(value) => field.handleChange(String(value))"
              @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
              @blur="field.handleBlur"
            />
          </templateInfoForm.Field>
          <templateInfoForm.Field v-slot="{ field }" name="description">
            <Textarea
              :model-value="field.state.value"
              maxlength="255"
              class="bg-base-white resize-none"
              @update:model-value="(value) => field.handleChange(String(value))"
            />
          </templateInfoForm.Field>
        </div>
      </section>

      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-template.sections.access.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-template.sections.access.description') }}
        </p>
        <DomainAccessForm
          ref="accessFormRef"
          :template-id="templateId"
          :show-bastion-config="false"
          :hardware-interfaces="hardwareInterfaces"
          :on-request-add-interface="handleAddInterfaceFromAccessForm"
        />
      </section>

      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-template.sections.hardware.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-template.sections.hardware.description') }}
        </p>
        <DomainHardwareForm ref="hardwareFormRef" :template-id="templateId" />
      </section>
    </template>
  </main>
</template>
