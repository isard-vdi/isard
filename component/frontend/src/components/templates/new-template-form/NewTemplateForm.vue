<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'

import {
  getDesktopDetailsOptions,
  getDesktopInfoOptions,
  createTemplateMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import DomainInfoSection from '@/components/domain/DomainInfoSection.vue'
import DomainSummary from '@/components/domain/DomainSummary.vue'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Field, FieldContent, FieldLabel } from '@/components/ui/field'
import { Button } from '@/components/ui/button'
import Switch from '@/components/ui/switch/Switch.vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import type { ErrorResponse } from '@/gen/oas/apiv4'
import { AllowedModal, type AllowedSelection } from '@/components/modal/allowed'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'

const { t } = useI18n()

interface Props {
  desktopId: string
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  templateCreated: [templateId: string]
}>()

// ------------------------------------------

const desktopId = ref<string>(props.desktopId)
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

const { data: desktopInfo, isPending: desktopInfoIsPending } = useQuery(
  getDesktopInfoOptions({
    path: {
      desktop_id: desktopId.value
    }
  })
)
const { data: desktopDetails, isPending: desktopDetailsIsPending } = useQuery(
  getDesktopDetailsOptions({
    path: {
      desktop_id: desktopId.value
    }
  })
)

const selectedImage = ref<DomainImageOutput | undefined>(undefined)
const showChangeImageModal = ref(false)

// The API derives an unrelated stock card from the new template id unless
// one is sent, so default to the card the preview already shows.
const currentImage = computed(() => selectedImage.value ?? desktopInfo.value?.image)
const imageUrl = computed(() => currentImage.value?.url || '')

function handleImageSelected(image: DomainImageOutput) {
  selectedImage.value = image
}

// The template is named after the desktop it comes from, not like it.
const infoSource = computed(() => ({
  name: desktopInfo.value?.name
    ? t(
        'views.new-template.form.sections.preview.fields.name.default',
        { desktop_name: desktopInfo.value.name },
        desktopInfo.value.name
      )
    : '',
  description: desktopInfo.value?.description ?? ''
}))

const infoRef = ref<InstanceType<typeof DomainInfoSection> | null>(null)
const enabled = ref(true)

const summary = computed(() => ({
  credentials: desktopDetails.value?.credentials,
  viewers: desktopDetails.value?.viewers,
  fullscreen: desktopDetails.value?.fullscreen,
  vcpu: desktopDetails.value?.vcpu,
  memory: desktopDetails.value?.memory,
  diskBus: desktopDetails.value?.disk_bus?.name,
  videos: desktopDetails.value?.videos.map((video) => video.name),
  interfaces: desktopDetails.value?.interfaces.map((iface) => iface.name),
  bootOrder: desktopDetails.value?.boot_order.map((boot) => boot.name),
  isos: desktopDetails.value?.isos?.map((iso) => iso.name),
  floppies: desktopDetails.value?.floppies?.map((floppy) => floppy.name),
  vgpus: desktopDetails.value?.reservables?.vgpus
}))

const createTemplateErrorCode = ref<string | undefined>(undefined)
const {
  mutate: createTemplate,
  isPending: createTemplateIsPending,
  isError: createTemplateIsError
} = useMutation({
  ...createTemplateMutation(),
  onSuccess: (data) => {
    emit('templateCreated', data.id)
  },
  onError: (error: Error) => {
    const errorResponse = error as unknown as ErrorResponse
    createTemplateErrorCode.value = errorResponse.description_code

    // Handle name conflict error
    if (errorResponse.description_code === 'new_template_name_exists') {
      infoRef.value?.form.getFieldInfo('name').instance?.setErrorMap({
        onSubmit: t('views.new-template.form.errors.fields.name.exists')
      })
    }
  }
})

const isPending = computed(() => {
  return (
    desktopInfoIsPending.value || desktopDetailsIsPending.value || createTemplateIsPending.value
  )
})

const isValid = computed(() => infoRef.value?.isValid ?? false)

// The card and the allowed selection live outside the info form.
const isDirty = computed(
  () =>
    !!infoRef.value?.isDirty ||
    !!selectedImage.value ||
    !enabled.value ||
    allowed.value.groups !== false ||
    allowed.value.users !== false
)

const handleSubmit = () => {
  if (!isValid.value || !infoRef.value) return

  const { name, description } = infoRef.value.getFormData()

  createTemplate({
    body: {
      desktop_id: desktopId.value,
      name,
      description,
      enabled: enabled.value,
      image: currentImage.value
        ? { id: currentImage.value.id, type: currentImage.value.type }
        : undefined,
      allowed: allowed.value
    }
  })
}

defineExpose({ isValid, isDirty, isPending, handleSubmit })

// Allowed
const handleSaveAllowed = (selection: AllowedSelection) => {
  allowed.value = selection
  showAllowedModal.value = false
}
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :current-image="currentImage"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <div class="w-full flex flex-col gap-[24px]">
    <Alert v-if="createTemplateIsError" variant="destructive" class="max-w-256 w-full mx-auto">
      <FeaturedIconOutline kind="outline" color="error" />

      <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
        t(`views.new-template.form.errors.title`)
      }}</AlertTitle>
      <AlertDescription>{{
        t(
          `api.new-template.errors.${createTemplateErrorCode}`,
          t('api.new-template.errors.generic')
        )
      }}</AlertDescription>
    </Alert>

    <DomainInfoSection
      ref="infoRef"
      :loading="desktopInfoIsPending"
      :source="infoSource"
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
          <h2 v-if="allowedSummary !== 'counts'" class="text-sm font-regular text-gray-warm-700">
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

      <DomainSummary :loading="desktopDetailsIsPending" v-bind="summary" />
    </div>
  </div>
</template>
