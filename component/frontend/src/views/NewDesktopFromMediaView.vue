<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { z } from 'zod'
import {
  createDesktopFromMediaMutation,
  checkQuotaNewDesktopOptions,
  checkStoragePoolCreationAvailabilityOptions,
  getMediaInstallsOptions,
  getUserDesktopsQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertModal, QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { Skeleton } from '@/components/ui/skeleton'
import OsTemplateSelect from '@/components/new-desktop/OsTemplateSelect.vue'
import DomainConfigurationPanel from '@/components/domain/DomainConfigurationPanel.vue'
import type { DomainConfigurationDefaults } from '@/components/domain/DomainConfigurationSection.vue'
import Step3Creating from '@/components/new-desktop/Step3Creating.vue'
import { FormHeader } from '@/components/form-header'
import { toGuestProperties, toImageInput, toMediaHardware } from '@/lib/domainPayload'
import router from '@/router'
import type { DomainImageOutput, MediaKindEnum, VirtInstallItem } from '@/gen/oas/apiv4/types.gen'

const { t } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()

const mediaId = computed(() => route.params.mediaId as string)
const mediaKind = computed(() => (route.query.kind as string) || 'iso')

// No desktop id yet to derive a card from, so pick one of the 48 stock cards
// up front and let the preview show what will be created. The id carries the
// extension, as the backend stores it everywhere else (`Cards.get_card`).
const stockCardNumber = Math.floor(Math.random() * 48) + 1
const desktopImage = ref<DomainImageOutput>({
  id: `${stockCardNumber}.jpg`,
  type: 'stock',
  url: `/assets/img/desktops/stock/${stockCardNumber}.jpg`
})

const quotaQuery = useQuery({
  ...checkQuotaNewDesktopOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const storageQuery = useQuery({
  ...checkStoragePoolCreationAvailabilityOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false,
  enabled: quotaQuery.isSuccess
})

const quotaCheckPassed = computed(() => storageQuery.isSuccess.value)

const {
  isPending: installsLoading,
  isError: installsError,
  data: installsData
} = useQuery(getMediaInstallsOptions())

type MediaInstallsResponse = VirtInstallItem[] | { installs?: VirtInstallItem[] }

const osTemplateOptions = computed(() => {
  const data = installsData.value as MediaInstallsResponse | undefined

  if (!data) return []

  return Array.isArray(data) ? data : (data.installs ?? [])
})
const hasOsTemplateOptions = computed(() => osTemplateOptions.value.length > 0)

// One source of truth for the seeds: the same object feeds the sub-forms and
// the summaries, so the two can no longer disagree.
const defaults: DomainConfigurationDefaults = {
  access: {
    credentials: { username: 'isard', password: '' },
    fullscreen: false,
    viewers: ['browser_vnc', 'file_spice']
  },
  hardware: {
    vcpus: 2,
    memory: 4,
    diskSize: 1,
    diskBus: 'default',
    videos: 'default',
    bootOrder: 'iso',
    interfaces: ['default'],
    reservables: { vgpus: [] }
  }
}

const summary = {
  credentials: defaults.access!.credentials,
  viewers: defaults.access!.viewers,
  fullscreen: defaults.access!.fullscreen,
  vcpu: defaults.hardware!.vcpus,
  memory: defaults.hardware!.memory,
  diskSize: defaults.hardware!.diskSize,
  diskBus: defaults.hardware!.diskBus,
  videos: [defaults.hardware!.videos!],
  bootOrder: [defaults.hardware!.bootOrder!],
  interfaces: defaults.hardware!.interfaces,
  vgpus: defaults.hardware!.reservables!.vgpus
}

const infoExtraDefaults = { os_template: '' }
const infoExtraSchema = { os_template: z.string().min(1) }

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)
const panelRef = ref<InstanceType<typeof DomainConfigurationPanel> | null>(null)

const areFormsValid = computed(
  () => (panelRef.value?.areFormsValid ?? false) && hasOsTemplateOptions.value
)

const isTouched = computed(() => panelRef.value?.isDirty ?? false)

const createButtonTooltip = computed(() => {
  if (areFormsValid.value) return undefined
  return {
    title: t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.title'),
    description: t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.description')
  }
})

const creationError = ref<string | null>(null)
const isCreating = ref(false)

const { mutate: submitCreateFromMedia } = useMutation({
  ...createDesktopFromMediaMutation(),
  onSuccess: async (data) => {
    await queryClient.invalidateQueries({ queryKey: getUserDesktopsQueryKey() })
    formHeaderRef.value?.allowLeave()
    router.push({
      name: 'single-desktop',
      params: {
        desktopId: data.id,
        action: 'desktop-created',
        origin: 'media'
      }
    })
  },
  onError: (error) => {
    creationError.value = 'description_code' in error ? error.description_code : 'generic'
    isCreating.value = false
  }
})

const handleSubmit = () => {
  if (!areFormsValid.value || !panelRef.value) return

  creationError.value = null
  isCreating.value = true

  const data = panelRef.value.getFormData()

  submitCreateFromMedia({
    body: {
      media_id: mediaId.value,
      kind: mediaKind.value as MediaKindEnum,
      os_template: data.extra.os_template as string,
      name: data.name,
      description: data.description.trim() ? data.description : undefined,
      guest_properties: toGuestProperties(data.access)!,
      hardware: toMediaHardware(data.hardware)!,
      image: toImageInput(data.image)
    }
  })
}
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="quotaQuery.isError.value"
    :title="t('components.desktops.quota-exceeded-modal.title')"
    :description="t('components.desktops.quota-exceeded-modal.description')"
    :cancel-label="t('components.desktops.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'media' }"
  />

  <!-- Storage Unavailable Modal -->
  <AlertModal
    :open="storageQuery.isError.value"
    level="danger"
    size="md"
    :title="t('components.desktops.storage-unavailable-modal.title')"
    :description="t('components.desktops.storage-unavailable-modal.description')"
    :close-on-backdrop-click="false"
    :show-close-button="false"
  >
    <template #footer>
      <Button hierarchy="primary" @click="router.push({ name: 'media' })">{{
        t('components.desktops.storage-unavailable-modal.go-to-media')
      }}</Button>
    </template>
  </AlertModal>

  <template v-if="quotaCheckPassed">
    <!-- Creating state -->
    <template v-if="isCreating && !creationError">
      <Step3Creating />
    </template>

    <template v-else>
      <!-- Header -->
      <FormHeader
        ref="formHeaderRef"
        :cancel-to="{ name: 'media' }"
        :confirm-cancel="isTouched"
        :next-label="t('views.new-desktop.step-2.buttons.create-desktop.label')"
        :next-disabled="!areFormsValid"
        :next-tooltip="createButtonTooltip"
        @next="handleSubmit"
      />

      <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
        <!-- Creation error -->
        <Alert v-if="creationError" variant="destructive">
          <AlertTitle>{{ t(`api.new-desktop.errors.${creationError}.title`) }}</AlertTitle>
          <AlertDescription>{{
            t(`api.new-desktop.errors.${creationError}.description`)
          }}</AlertDescription>
        </Alert>

        <DomainConfigurationPanel
          ref="panelRef"
          :info-extra-defaults="infoExtraDefaults"
          :info-extra-schema="infoExtraSchema"
          :image="desktopImage"
          show-disk-size
          :show-peripherals="false"
          :defaults="defaults"
          :summary="summary"
          context="new-desktop-from-media"
          @update:image="desktopImage = $event"
        >
          <template #info-extra="{ form }">
            <component :is="form.Field" v-slot="{ field }" name="os_template">
              <div class="pt-8">
                <h3 class="text-lg font-semibold text-gray-warm-900">
                  {{ t('views.new-desktop-from-media.os-template.title') }}
                </h3>
                <p class="text-sm font-regular mb-3">
                  {{ t('views.new-desktop-from-media.os-template.description') }}
                </p>
                <Skeleton v-if="installsLoading" class="h-10 w-full" />
                <OsTemplateSelect
                  v-else
                  :options="osTemplateOptions"
                  :disabled="installsError || !hasOsTemplateOptions"
                  :invalid="field.state.value === ''"
                  :placeholder="t('views.new-desktop-from-media.os-template.placeholder')"
                  :model-value="field.state.value"
                  @update:model-value="(v: string) => field.handleChange(String(v))"
                />
              </div>
            </component>
          </template>
        </DomainConfigurationPanel>
      </main>
    </template>
  </template>
</template>
