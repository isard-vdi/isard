<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { z } from 'zod'
import { useForm } from '@tanstack/vue-form'

import {
  getTemplateDetailsOptions,
  getTemplateDetailsQueryKey,
  getTemplateInfoQueryKey,
  updateTemplateMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { InputField } from '@/components/input-field'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { describeApiError } from '@/lib/api-errors'
import type { DomainImageFile, DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'

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

const selectedImage = ref<DomainImageOutput | undefined>(undefined)
const pendingImageFile = ref<DomainImageFile | undefined>(undefined)
const showChangeImageModal = ref(false)
const imageUrl = computed(() => selectedImage.value?.url || '')

function handleImageSelected(image: DomainImageOutput & { file?: DomainImageFile }) {
  selectedImage.value = image
  pendingImageFile.value = image.file
}

// --------------------------------------------------
// Form
// --------------------------------------------------

const templateInfoFormSchema = z.object({
  name: z.string().min(4).max(50),
  description: z.string().max(255).optional()
})

const defaultValues = reactive({ name: '', description: '' })

const templateInfoForm = useForm({
  defaultValues,
  validators: { onChange: templateInfoFormSchema }
})

const infoValid = templateInfoForm.useStore((state) => state.isValid)

watch(
  templateDetails,
  (data) => {
    if (!data) return
    templateInfoForm.setFieldValue('name', data.name)
    templateInfoForm.setFieldValue('description', data.description || '')
    selectedImage.value = (data as { image?: DomainImageOutput }).image
    pendingImageFile.value = undefined
  },
  { immediate: true }
)

function isInvalid(field: any) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

// --------------------------------------------------
// Sub-forms
// --------------------------------------------------

const accessFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
} | null>(null)

const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  limitedFields: Record<string, unknown> | null
  addInterface: (ifaceId: string) => boolean | undefined
  removeInterface: (ifaceId: string) => void
  interfaces: string[]
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  return hardwareFormRef.value?.addInterface(ifaceId)
}

const hardwareFormIsValid = computed(() => hardwareFormRef.value?.isValid ?? true)
const accessFormIsValid = computed(() => accessFormRef.value?.isValid ?? true)

const areFormsValid = computed(
  () => infoValid.value && hardwareFormIsValid.value && accessFormIsValid.value
)

// --------------------------------------------------
// Mutation
// --------------------------------------------------

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
    router.push({ name: 'templates' })
  },
  onError: (error: unknown) => {
    submitError.value = describeApiError(error, { t, te }, 'edit-template')
  }
})

// --------------------------------------------------
// Submit
// --------------------------------------------------

const showAccessCustomization = ref(false)
const showHardwareCustomization = ref(false)

const handleSubmit = () => {
  if (!areFormsValid.value) return
  submitError.value = null

  const accessData = accessFormRef.value?.getFormData()
  const hardwareData = hardwareFormRef.value?.getFormData()

  submitEdit({
    path: { template_id: templateId.value },
    body: {
      name: templateInfoForm.getFieldValue('name'),
      description: templateInfoForm.getFieldValue('description'),
      image: selectedImage.value
        ? {
            id: selectedImage.value.id,
            type: selectedImage.value.type,
            ...(pendingImageFile.value ? { file: pendingImageFile.value } : {})
          }
        : undefined,
      guest_properties: {
        credentials: accessData?.credentials ?? templateDetails.value?.credentials,
        fullscreen: accessData?.fullscreen ?? templateDetails.value?.fullscreen,
        viewers: accessData?.viewers ?? templateDetails.value?.viewers
      } as any,
      hardware: {
        vcpus: hardwareData?.vcpus ?? templateDetails.value?.vcpu,
        memory: hardwareData?.memory ?? templateDetails.value?.memory,
        disk_bus: hardwareData?.diskBus ?? templateDetails.value?.disk_bus,
        videos: hardwareData
          ? [hardwareData.videos]
          : templateDetails.value?.videos?.map((v: any) => v.id),
        interfaces:
          hardwareData?.interfaces ?? templateDetails.value?.interfaces?.map((i: any) => i.id),
        boot_order: hardwareData
          ? [hardwareData.bootOrder]
          : templateDetails.value?.boot_order?.map((b: any) => b.id),
        isos: hardwareData?.isos ?? templateDetails.value?.isos?.map((i: any) => i.id) ?? [],
        floppies:
          hardwareData?.floppies ??
          (templateDetails.value as any)?.floppies?.map((f: any) => f.id) ??
          []
      } as any,
      reservables: {
        vgpus: hardwareData?.reservables?.vgpus ?? templateDetails.value?.reservables?.vgpus ?? null
      } as any
    }
  })
}
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :domain-id="templateId"
    :current-image="selectedImage"
    :persist-on-save="false"
    :allow-upload="false"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <div
    class="flex flex-col-reverse md:flex-row items-start justify-between max-w-480 w-full mx-auto mb-8 gap-4"
  >
    <div class="flex flex-col gap-1"></div>

    <div class="flex gap-4 md:w-auto w-full justify-end">
      <Button :as="RouterLink" :to="{ name: 'templates' }" hierarchy="link-color">{{
        t('views.edit-template.header.cancel')
      }}</Button>

      <Button
        :disabled="!areFormsValid || submitPending || templateDetailsIsPending"
        :icon="submitPending ? 'loading-02' : ''"
        icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
        @click="handleSubmit"
        >{{ t('views.edit-template.header.save') }}</Button
      >
    </div>
  </div>

  <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
    <div class="w-full flex flex-col gap-6">
      <Alert v-if="submitError" variant="destructive" class="max-w-256 w-full mx-auto">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
          t('views.edit-template.errors.title')
        }}</AlertTitle>
        <AlertDescription>{{ submitError }}</AlertDescription>
      </Alert>

      <!-- Preview Section -->
      <div class="flex flex-col gap-4">
        <div class="flex flex-col">
          <h2 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-template.form.sections.preview.title') }}
          </h2>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-template.form.sections.preview.subtitle') }}
          </p>
        </div>

        <div v-if="templateDetailsIsPending" class="flex gap-2">
          <Skeleton class="h-16 w-47 rounded-l-2xl shrink-0" />
          <Skeleton class="h-16 w-full rounded-r-2xl" />
        </div>
        <div
          v-else
          class="grid gap-y-2 grid-flow-col"
          :style="{
            gridTemplateColumns:
              'var(--spacing-48) minmax(var(--spacing-48), var(--spacing-120)) auto'
          }"
        >
          <div class="grid grid-rows-subgrid row-span-3">
            <div
              class="row-start-2 w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover relative"
              :style="{
                backgroundImage: imageUrl ? `url(${imageUrl})` : undefined
              }"
            >
              <Button
                class="absolute top-1 left-1 rounded-tl-xl"
                hierarchy="secondary-gray"
                size="sm"
                icon="image-plus"
                @click="showChangeImageModal = true"
              />
            </div>
          </div>

          <form class="contents" @submit.prevent="handleSubmit">
            <templateInfoForm.Field v-slot="{ field }" name="name" class="contents">
              <Field :data-invalid="isInvalid(field)" class="contents">
                <div class="text-sm font-semibold px-4">
                  <FieldLabel :for="field.name">{{
                    t('views.new-template.form.sections.preview.fields.name.label')
                  }}</FieldLabel>
                </div>
                <div
                  class="w-full bg-base-white h-16 flex items-center border-gray-warm-200 px-4 border-y pr-0"
                >
                  <InputField
                    :id="field.name"
                    :name="field.name"
                    :model-value="field.state.value"
                    :placeholder="
                      t('views.new-template.form.sections.preview.fields.name.placeholder')
                    "
                    :aria-invalid="isInvalid(field)"
                    :destructive="isInvalid(field)"
                    autocomplete="off"
                    type="text"
                    maxlength="50"
                    @blur="field.handleBlur"
                    @input="field.handleChange($event.target.value)"
                  />
                </div>
                <div class="text-sm font-semibold px-4">
                  <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
                </div>
              </Field>
            </templateInfoForm.Field>
            <templateInfoForm.Field v-slot="{ field }" name="description" class="contents">
              <Field :data-invalid="isInvalid(field)" class="contents">
                <div class="text-sm font-semibold px-4">
                  <FieldLabel :for="field.name">{{
                    t('views.new-template.form.sections.preview.fields.description.label')
                  }}</FieldLabel>
                </div>
                <div
                  class="w-full bg-base-white h-16 flex items-center border-gray-warm-200 px-4 border-y rounded-r-2xl border-r"
                >
                  <InputField
                    :id="field.name"
                    :name="field.name"
                    :model-value="field.state.value"
                    :placeholder="
                      t('views.new-template.form.sections.preview.fields.description.placeholder')
                    "
                    :aria-invalid="isInvalid(field)"
                    :destructive="isInvalid(field)"
                    autocomplete="off"
                    type="text"
                    maxlength="255"
                    @blur="field.handleBlur"
                    @input="field.handleChange($event.target.value)"
                  />
                </div>
                <div class="text-sm font-semibold px-4">
                  <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
                </div>
              </Field>
            </templateInfoForm.Field>
          </form>
        </div>
      </div>

      <!-- Access & Hardware Section -->
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-0.5">
          <h2 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-template.form.sections.access.title') }}
          </h2>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-template.form.sections.access.subtitle') }}
          </p>
        </div>

        <Skeleton v-if="templateDetailsIsPending" class="h-48 w-full rounded-2xl" />
        <div v-else class="flex flex-col gap-0">
          <DomainAccessSummary
            :credentials="templateDetails?.credentials as any"
            :viewers="templateDetails?.viewers"
            :fullscreen="templateDetails?.fullscreen"
          />
          <Separator orientation="horizontal" class="my-8">
            <template #default>
              <Button
                hierarchy="secondary-gray"
                size="sm"
                :icon="showAccessCustomization ? 'chevron-up' : 'chevron-down'"
                @click="showAccessCustomization = !showAccessCustomization"
              >
                {{
                  t(
                    `views.new-desktop.step-2.access.${showAccessCustomization ? 'hide' : 'show'}-access-customization`
                  )
                }}
              </Button>
            </template>
          </Separator>
          <div v-show="showAccessCustomization" class="my-8">
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-template.form.sections.access.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-template.form.sections.access.subtitle') }}
            </p>
            <DomainAccessForm
              ref="accessFormRef"
              :template-id="templateId"
              :hardware-interfaces="hardwareInterfaces"
              :on-request-add-interface="handleAddInterfaceFromAccessForm"
            />
          </div>

          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-template.form.sections.hardware.title') }}
          </h3>
          <p class="text-sm font-regular mb-6">
            {{ t('views.new-template.form.sections.hardware.subtitle') }}
          </p>
          <DomainHardwareSummary
            :vcpu="templateDetails?.vcpu"
            :memory="templateDetails?.memory"
            :disk-bus="templateDetails?.disk_bus"
            :videos="templateDetails?.videos?.map((v) => v.name)"
            :interfaces="templateDetails?.interfaces?.map((i) => i.name)"
            :boot-order="templateDetails?.boot_order?.map((b) => b.name)"
            :isos="templateDetails?.isos?.map((i) => i.name)"
            :floppies="templateDetails?.floppies?.map((f) => f.name)"
            :loading="templateDetailsIsPending"
            :vgpus="templateDetails?.reservables?.vgpus"
          />
          <Separator orientation="horizontal" class="my-8">
            <template #default>
              <Button
                hierarchy="secondary-gray"
                size="sm"
                :icon="showHardwareCustomization ? 'chevron-up' : 'chevron-down'"
                @click="showHardwareCustomization = !showHardwareCustomization"
              >
                {{
                  t(
                    `views.new-desktop.step-2.hardware-summary.${showHardwareCustomization ? 'hide' : 'show'}-hardware-customization`
                  )
                }}
              </Button>
            </template>
          </Separator>
          <div v-show="showHardwareCustomization" class="my-8">
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.all-hardware.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-desktop.step-2.all-hardware.description') }}
            </p>
            <DomainHardwareForm ref="hardwareFormRef" :template-id="templateId" />
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
