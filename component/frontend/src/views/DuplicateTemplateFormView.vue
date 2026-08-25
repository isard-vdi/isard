<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'

import {
  getTemplateInfoOptions,
  getTemplateDetailsOptions,
  duplicateTemplateMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ErrorResponse } from '@/gen/oas/apiv4'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
import { checkQuotaNewTemplateOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { QuotaExceededModal } from '@/components/modal'
import { AllowedModal, type AllowedSelection } from '@/components/modal/allowed'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import DomainInfoSection from '@/components/domain/DomainInfoSection.vue'
import DomainSummary from '@/components/domain/DomainSummary.vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Field, FieldContent, FieldLabel } from '@/components/ui/field'
import { FormHeader } from '@/components/form-header'
import { Switch } from '@/components/ui/switch'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// --------------------------------------------------
// Quota check
// --------------------------------------------------

const quotaQuery = useQuery({
  ...checkQuotaNewTemplateOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const quotaCheckPassed = computed(() => quotaQuery.isSuccess.value)

// --------------------------------------------------

const templateId = ref<string>(route.params.templateId as string)

const { data: templateInfo, isPending: templateInfoIsPending } = useQuery(
  getTemplateInfoOptions({
    path: {
      template_id: templateId.value
    }
  })
)
const { data: templateDetails, isPending: templateDetailsIsPending } = useQuery(
  getTemplateDetailsOptions({
    path: {
      template_id: templateId.value
    }
  })
)

const selectedImage = ref<DomainImageOutput | undefined>(undefined)
const showChangeImageModal = ref(false)

const currentImage = computed(() => selectedImage.value ?? templateInfo.value?.image)
const imageUrl = computed(() => currentImage.value?.url || '')

function handleImageSelected(image: DomainImageOutput) {
  selectedImage.value = image
}

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)

const infoRef = ref<InstanceType<typeof DomainInfoSection> | null>(null)
const enabled = ref(true)

const showAllowedModal = ref<boolean>(false)

const allowed = ref<AllowedSelection>({ groups: false, users: false })

const bucketCount = (bucket: boolean | string[]) => (Array.isArray(bucket) ? bucket.length : 0)
const isEveryone = (bucket: boolean | string[]) => Array.isArray(bucket) && bucket.length === 0

const allowedGroupCount = computed(() => bucketCount(allowed.value.groups))
const allowedUserCount = computed(() => bucketCount(allowed.value.users))

const allowedSummary = computed<'everyone' | 'nobody' | 'counts'>(() => {
  if (isEveryone(allowed.value.groups) || isEveryone(allowed.value.users)) return 'everyone'
  return allowedGroupCount.value + allowedUserCount.value === 0 ? 'nobody' : 'counts'
})

const handleSaveAllowed = (selection: AllowedSelection) => {
  allowed.value = selection
  showAllowedModal.value = false
}

const isValid = computed(() => infoRef.value?.isValid ?? false)

const isDirty = computed(
  () =>
    !!infoRef.value?.isDirty ||
    !!selectedImage.value ||
    !enabled.value ||
    allowed.value.groups !== false ||
    allowed.value.users !== false
)

const summary = computed(() => ({
  credentials: templateDetails.value?.credentials,
  viewers: templateDetails.value?.viewers,
  fullscreen: templateDetails.value?.fullscreen,
  vcpu: templateDetails.value?.vcpu,
  memory: templateDetails.value?.memory,
  diskBus: templateDetails.value?.disk_bus?.name,
  videos: templateDetails.value?.videos.map((video) => video.name),
  interfaces: templateDetails.value?.interfaces.map((iface) => iface.name),
  bootOrder: templateDetails.value?.boot_order.map((boot) => boot.name),
  isos: templateDetails.value?.isos?.map((iso) => iso.name),
  vgpus: templateDetails.value?.reservables?.vgpus
}))

const duplicateTemplateErrorCode = ref<string | undefined>(undefined)
const {
  mutate: duplicateTemplate,
  isPending: duplicateTemplateIsPending,
  isError: duplicateTemplateIsError
} = useMutation({
  ...duplicateTemplateMutation(),
  onSuccess: (data) => {
    formHeaderRef.value?.allowLeave()
    router.push({ name: 'templates', params: { templateId: data.id } })
  },
  onError: (error: unknown) => {
    // The generated client throws the parsed error body (an ErrorResponse),
    // not an Error with a JSON string in .message — read description_code off
    // it directly. The backend returns `template_failed` when the source
    // template is in Failed status.
    const errorResponse = error as ErrorResponse
    duplicateTemplateErrorCode.value = errorResponse?.description_code

    // Handle name conflict error
    if (errorResponse?.description_code === 'new_template_name_exists') {
      infoRef.value?.form.getFieldInfo('name').instance?.setErrorMap({
        onSubmit: t('views.new-template.form.errors.fields.name.exists')
      })
    }
  }
})

const isPending = computed(() => {
  return (
    templateInfoIsPending.value ||
    templateDetailsIsPending.value ||
    duplicateTemplateIsPending.value
  )
})

const handleSubmit = () => {
  if (!isValid.value || !infoRef.value) return

  const { name, description } = infoRef.value.getFormData()

  duplicateTemplate({
    path: {
      template_id: templateId.value
    },
    body: {
      name,
      description,
      enabled: enabled.value,
      image: selectedImage.value
        ? { id: selectedImage.value.id, type: selectedImage.value.type }
        : undefined,
      allowed: allowed.value
    }
  })
}
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :current-image="currentImage"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="quotaQuery.isError.value"
    :title="t('components.templates.quota-exceeded-modal.title')"
    :description="t('components.templates.quota-exceeded-modal.description')"
    :cancel-label="t('components.templates.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'templates' }"
  />

  <template v-if="quotaCheckPassed">
    <FormHeader
      ref="formHeaderRef"
      :cancel-to="{ name: 'templates' }"
      :confirm-cancel="isDirty"
      :next-label="t('views.new-template.header.create-template')"
      :next-disabled="!isValid"
      :next-pending="isPending"
      @next="handleSubmit"
    />

    <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
      <div class="w-full flex flex-col gap-6">
        <Alert
          v-if="duplicateTemplateIsError"
          variant="destructive"
          class="max-w-256 w-full mx-auto"
        >
          <FeaturedIconOutline kind="outline" color="error" />

          <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
            t(`views.new-template.form.errors.title`)
          }}</AlertTitle>
          <AlertDescription>{{
            t(`api.new-template.errors.${duplicateTemplateErrorCode}`)
          }}</AlertDescription>
        </Alert>

        <DomainInfoSection
          ref="infoRef"
          :loading="templateInfoIsPending"
          :source="templateInfo"
          :image-url="imageUrl"
          entity="templates"
          preview="template-row"
          @change-image="showChangeImageModal = true"
        />

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="flex flex-col gap-[16px]">
            <div class="flex flex-col gap-0.5">
              <h1 class="text-lg font-semibold text-gray-warm-900">
                {{ t('views.new-template.form.sections.visibility.title') }}
              </h1>
              <h2 class="text-sm font-regular text-gray-warm-700">
                {{ t('views.new-template.form.sections.visibility.subtitle') }}
              </h2>
            </div>

            <Field orientation="horizontal">
              <Switch id="enabled" v-model="enabled" name="enabled" />
              <FieldContent>
                <FieldLabel for="enabled">{{
                  t('views.new-template.form.sections.visibility.label')
                }}</FieldLabel>
              </FieldContent>
            </Field>
          </div>
          <div class="flex flex-col gap-[16px]">
            <div class="flex flex-col gap-0.5">
              <h1 class="text-lg font-semibold text-gray-warm-900">
                {{ t('views.new-template.form.sections.alloweds.title') }}
              </h1>
              <h2
                v-if="allowedSummary !== 'counts'"
                class="text-sm font-regular text-gray-warm-700"
              >
                {{ t(`views.new-template.form.sections.alloweds.subtitle-${allowedSummary}`) }}
              </h2>
              <i18n-t
                v-else
                keypath="views.new-template.form.sections.alloweds.subtitle"
                tag="h2"
                class="text-sm font-regular text-gray-warm-700"
              >
                <template #groups>
                  <b>{{ t('users.count.groups', allowedGroupCount) }}</b>
                </template>
                <template #users>
                  <b>{{ t('users.count.users', allowedUserCount) }}</b>
                </template>
              </i18n-t>
            </div>

            <div>
              <Button icon="plus" hierarchy="secondary-gray" @click="showAllowedModal = true">{{
                t('views.new-template.form.sections.alloweds.button')
              }}</Button>
              <AllowedModal
                :open="showAllowedModal"
                item-type="template"
                :selection="allowed"
                @close="showAllowedModal = false"
                @save="handleSaveAllowed"
              />
            </div>
          </div>
        </div>

        <div class="flex flex-col gap-[16px]">
          <div class="flex flex-col gap-[2px]">
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-template.form.sections.hardware.title') }}
            </h1>
            <h2 class="text-sm font-regular text-gray-warm-700">
              {{ t('views.new-template.form.sections.hardware.subtitle') }}
            </h2>
          </div>

          <DomainSummary kind="template" :loading="templateDetailsIsPending" v-bind="summary" />
        </div>
      </div>
    </main>
  </template>
</template>
