<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'
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
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import { DesktopCardBase, DesktopCardHeader } from '@/components/desktop-card'
import Step3Creating from '@/components/new-desktop/Step3Creating.vue'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import router from '@/router'
import type { MediaKindEnum, VirtInstallItem } from '@/gen/oas/apiv4/types.gen'

const { t } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()

const mediaId = computed(() => route.params.mediaId as string)
const mediaKind = computed(() => (route.query.kind as string) || 'iso')

const stockImageId = (Math.floor(Math.random() * 48) + 1).toString()
const desktopImage = {
  id: stockImageId,
  type: 'stock',
  url: `/assets/img/desktops/stock/${stockImageId}.jpg`
}

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

const isNameInvalid = (value: string) => !desktopInfoFormSchema.shape.name.safeParse(value).success

const defaultHardware = {
  vcpu: 2,
  memory: 4,
  diskSize: 1,
  diskBus: 'default',
  videos: ['default'],
  bootOrder: ['iso'],
  isos: [] as string[],
  floppies: [] as string[],
  vgpus: [] as string[],
  interfaces: ['default']
}

const defaultAccess = {
  credentials: {
    username: 'isard',
    password: 'pirineus'
  },
  fullscreen: false,
  viewers: ['browser_vnc', 'file_spice']
}

const desktopInfoFormSchema = z.object({
  name: z.string().min(4).max(50),
  description: z.string().max(255),
  os_template: z.string().min(1)
})

const defaultValues = reactive({
  name: '',
  description: '',
  os_template: ''
})

const desktopInfoForm = useForm({
  defaultValues,
  validators: {
    onChange: desktopInfoFormSchema
  }
})

const infoFormValues = desktopInfoForm.useStore((state) => state.values)
const infoValid = desktopInfoForm.useStore((state) => state.isValid)
const infoIsTouched = desktopInfoForm.useStore((state) => !state.isPristine)

const accessFormRef = ref<{ getFormData: () => any; isValid: boolean } | null>(null)
const hardwareFormRef = ref<{
  getFormData: () => any
  isValid: boolean
  limitedFields: any
  interfaces: { value: string[] }
  addInterface: (ifaceId: string) => boolean | undefined
} | null>(null)

const hardwareInterfaces = ref<string[]>(defaultHardware.interfaces)

function handleHardwareInterfacesUpdate(interfaces: string[]) {
  hardwareInterfaces.value = interfaces
}

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  return hardwareFormRef.value?.addInterface(ifaceId)
}

const hardwareFormIsValid = computed(() => hardwareFormRef.value?.isValid ?? true)

const areFormsValid = computed(() => {
  return (
    infoIsTouched.value &&
    infoValid.value &&
    hasOsTemplateOptions.value &&
    hardwareFormIsValid.value &&
    (accessFormRef.value?.isValid ?? true)
  )
})

const showAccessCustomization = ref(false)
const showHardwareCustomization = ref(false)

const toggleAccessCustomization = () => {
  showAccessCustomization.value = !showAccessCustomization.value
}
const toggleHardwareCustomization = () => {
  showHardwareCustomization.value = !showHardwareCustomization.value
}

const creationError = ref<string | null>(null)
const isCreating = ref(false)

const { mutate: submitCreateFromMedia } = useMutation({
  ...createDesktopFromMediaMutation(),
  onSuccess: async (data) => {
    await queryClient.invalidateQueries({ queryKey: getUserDesktopsQueryKey() })
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
  if (!areFormsValid.value) return

  creationError.value = null
  isCreating.value = true

  const accessSettings = accessFormRef.value?.getFormData()
  const hardwareSettings = hardwareFormRef.value?.getFormData()
  const descriptionValue = desktopInfoForm.getFieldValue('description') as string

  submitCreateFromMedia({
    body: {
      media_id: mediaId.value,
      kind: mediaKind.value as MediaKindEnum,
      os_template: desktopInfoForm.getFieldValue('os_template') as string,
      name: desktopInfoForm.getFieldValue('name') as string,
      description: descriptionValue.trim() ? descriptionValue : undefined,
      guest_properties: {
        credentials: accessSettings?.credentials,
        fullscreen: accessSettings?.fullscreen,
        viewers: accessSettings?.viewers
      },
      hardware: {
        vcpus: hardwareSettings?.vcpus,
        memory: hardwareSettings?.memory,
        disk_bus: hardwareSettings?.diskBus,
        disk_size: hardwareSettings?.diskSize,
        boot_order: [hardwareSettings?.bootOrder],
        videos: [hardwareSettings?.videos],
        interfaces: hardwareSettings?.interfaces,
        reservables: {
          vgpus: hardwareSettings?.reservables?.vgpus ?? []
        }
      },
      image: desktopImage
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
      <header
        class="flex flex-col md:flex-row items-start justify-center max-w-480 w-full mx-auto mb-8 gap-4"
      >
        <div class="flex flex-row items-center gap-4 w-full">
          <Button
            :as="RouterLink"
            :to="{ name: 'media' }"
            hierarchy="link-color"
            icon="arrow-left"
            class="pb-6 pt-0 pl-0"
          >
            {{ t('views.new-desktop.header.cancel') }}
          </Button>
        </div>
        <div class="flex flex-row items-center justify-end gap-4 w-full">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button hierarchy="primary" :disabled="!areFormsValid" @click="handleSubmit">
                  {{ t('views.new-desktop.step-2.buttons.create-desktop.label') }}
                </Button>
              </TooltipTrigger>
              <TooltipContent
                v-if="!areFormsValid"
                :title="t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.title')"
                :subtitle="
                  t('views.new-desktop.step-2.buttons.create-desktop.disabled-tooltip.description')
                "
                side="top"
              />
            </Tooltip>
          </TooltipProvider>
        </div>
      </header>

      <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
        <!-- Creation error -->
        <Alert v-if="creationError" variant="destructive">
          <AlertTitle>{{ t(`api.new-desktop.errors.${creationError}.title`) }}</AlertTitle>
          <AlertDescription>{{
            t(`api.new-desktop.errors.${creationError}.description`)
          }}</AlertDescription>
        </Alert>

        <!-- Preview + Desktop Information -->
        <div class="flex gap-6">
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-gray-warm-900">
              {{ t('views.new-desktop.step-2.preview.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-desktop.step-2.preview.description') }}
            </p>
            <DesktopCardBase :image-url="desktopImage.url" desktop-kind="persistent">
              <template #header>
                <DesktopCardHeader
                  :name="infoFormValues.name"
                  :description="infoFormValues.description"
                />
              </template>
              <template #footer>
                <Button
                  icon="play"
                  icon-class="fill-current"
                  hierarchy="secondary-color"
                  size="sm"
                  class="shrink-0"
                  disabled
                >
                  {{ t('components.desktops.desktop-card.status.stopped.action') }}
                </Button>
              </template>
            </DesktopCardBase>
          </div>
          <div class="flex-1">
            <div class="mb-6">
              <h3 class="text-lg font-semibold text-gray-warm-900">
                {{ t('views.new-desktop.step-2.desktop-information.title') }}
              </h3>
              <p class="text-sm font-regular mb-6">
                {{ t('views.new-desktop.step-2.desktop-information.description') }}
              </p>
              <div class="flex flex-col gap-3">
                <desktopInfoForm.Field v-slot="{ field }" name="name">
                  <InputField
                    :id="field.name"
                    :name="field.name"
                    :model-value="field.state.value"
                    :destructive="isNameInvalid(field.state.value)"
                    :aria-invalid="isNameInvalid(field.state.value)"
                    :placeholder="t('components.domain.info.name.placeholder')"
                    maxlength="50"
                    autofocus
                    @update:model-value="(value) => field.handleChange(String(value))"
                    @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
                    @blur="field.handleBlur"
                  />
                </desktopInfoForm.Field>

                <desktopInfoForm.Field v-slot="{ field }" name="description">
                  <Textarea
                    :model-value="field.state.value"
                    maxlength="255"
                    class="bg-base-white resize-none"
                    :placeholder="t('components.domain.info.description.placeholder')"
                    @update:model-value="(value) => field.handleChange(String(value))"
                  />
                </desktopInfoForm.Field>

                <desktopInfoForm.Field v-slot="{ field }" name="os_template">
                  <div class="pt-8">
                    <h3 class="text-lg font-semibold text-gray-warm-900">
                      {{ t('views.new-desktop-from-media.os-template.title') }}
                    </h3>
                    <p class="text-sm font-regular mb-3">
                      {{ t('views.new-desktop-from-media.os-template.description') }}
                    </p>
                    <div v-if="installsLoading" class="flex flex-col gap-2">
                      <Skeleton class="h-10 w-full" />
                    </div>
                    <div v-else>
                      <Select
                        :disabled="installsError || !hasOsTemplateOptions"
                        :model-value="field.state.value"
                        @update:model-value="(v) => field.handleChange(String(v))"
                      >
                        <SelectTrigger
                          :class="field.state.value === '' ? 'w-full ring-3 ring-error' : 'w-full'"
                          :aria-invalid="field.state.value === ''"
                        >
                          <SelectValue
                            :placeholder="t('views.new-desktop-from-media.os-template.placeholder')"
                          />
                        </SelectTrigger>
                        <SelectContent position="item-aligned">
                          <SelectItem
                            v-for="install in osTemplateOptions"
                            :key="install.id"
                            :value="install.id"
                          >
                            {{ install.name }}
                            <span v-if="install.vers" class="text-gray-warm-500 ml-1">
                              ({{ install.vers }})
                            </span>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </desktopInfoForm.Field>
              </div>
            </div>
          </div>
        </div>

        <!-- Access summary + customization -->
        <div class="mt-8">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-desktop.step-2.access.title') }}
          </h3>
          <p class="text-sm font-regular mb-6">
            {{ t('views.new-desktop.step-2.access.description') }}
          </p>
          <DomainAccessSummary
            :credentials="defaultAccess.credentials"
            :viewers="defaultAccess.viewers"
            :fullscreen="defaultAccess.fullscreen"
          />
          <Separator orientation="horizontal" class="my-8">
            <template #default>
              <Button
                hierarchy="secondary-gray"
                size="sm"
                :icon="showAccessCustomization ? 'chevron-up' : 'chevron-down'"
                @click="toggleAccessCustomization"
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
              {{ t('views.new-desktop.step-2.all-access.title') }}
            </h3>
            <p class="text-sm font-regular mb-6">
              {{ t('views.new-desktop.step-2.all-access.description') }}
            </p>
            <DomainAccessForm
              ref="accessFormRef"
              :show-bastion-config="false"
              :viewers="defaultAccess.viewers"
              :credentials="defaultAccess.credentials"
              :fullscreen="defaultAccess.fullscreen"
              :hardware-interfaces="hardwareInterfaces"
              :on-request-add-interface="handleAddInterfaceFromAccessForm"
            />
          </div>
        </div>

        <!-- Hardware summary + customization -->
        <div>
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-desktop.step-2.hardware-summary.title') }}
          </h3>
          <p class="text-sm font-regulaDr mb-6">
            {{ t('views.new-desktop.step-2.hardware-summary.description') }}
          </p>

          <DomainHardwareSummary
            :vcpu="defaultHardware.vcpu"
            :memory="defaultHardware.memory"
            :disk-size="defaultHardware.diskSize"
            :disk-bus="defaultHardware.diskBus"
            :videos="defaultHardware.videos"
            :interfaces="defaultHardware.interfaces"
            :boot-order="defaultHardware.bootOrder"
            :isos="defaultHardware.isos"
            :floppies="defaultHardware.floppies"
            :vgpus="defaultHardware.vgpus"
          />
        </div>
        <Separator orientation="horizontal" class="my-6">
          <template #default>
            <Button
              hierarchy="secondary-gray"
              size="sm"
              :icon="showHardwareCustomization ? 'chevron-up' : 'chevron-down'"
              @click="toggleHardwareCustomization"
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
          <DomainHardwareForm
            ref="hardwareFormRef"
            :show-disk-size="true"
            :show-peripherals="false"
            boot-order="iso"
            :interfaces="defaultHardware.interfaces"
            @update:interfaces="handleHardwareInterfacesUpdate"
          />
        </div>
      </main>
    </template>
  </template>
</template>
