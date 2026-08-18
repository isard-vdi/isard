<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type * as z from 'zod'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
import DomainInfoSection, {
  type DomainInfoPreview,
  type DomainKind
} from '@/components/domain/DomainInfoSection.vue'
import DomainConfigurationSection, {
  type DomainConfigurationContext,
  type DomainConfigurationDefaults
} from '@/components/domain/DomainConfigurationSection.vue'
import type { DomainSummaryData } from '@/components/domain/DomainSummary.vue'
import type { DomainInfoSource } from '@/composables/useDomainInfoForm'
import type { DomainImageFile, DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import type { AccessFormData, HardwareFormData } from '@/lib/domainPayload'

export interface DomainConfigurationPanelData {
  name: string
  description: string
  /** Fields declared through `infoExtraSchema`, e.g. `{ os_template: 'win10' }`. */
  extra: Record<string, unknown>
  kind: 'persistent' | 'nonpersistent'
  access: AccessFormData | undefined
  hardware: HardwareFormData | undefined
  image: DomainImageOutput | undefined
  /** Only set when the viewer uploaded a card in this session. */
  imageFile: DomainImageFile | undefined
}

const props = withDefaults(
  defineProps<{
    templateId?: string
    desktopId?: string
    loading?: boolean

    info?: DomainInfoSource
    infoExtraDefaults?: Record<string, string>
    infoExtraSchema?: z.ZodRawShape
    showKindSelector?: boolean
    kind?: DomainKind
    entity?: 'desktops' | 'templates'
    preview?: DomainInfoPreview
    context?: DomainConfigurationContext

    alwaysShowConfiguration?: boolean
    showBastionConfig?: boolean
    showCustomDomains?: boolean
    showDiskSize?: boolean
    showPeripherals?: boolean
    summary?: DomainSummaryData
    defaults?: DomainConfigurationDefaults

    image?: DomainImageOutput
    imageDomainId?: string
    imagePersistOnSave?: boolean
    imageAllowUpload?: boolean
  }>(),
  {
    templateId: undefined,
    desktopId: undefined,
    loading: false,
    info: undefined,
    infoExtraDefaults: undefined,
    infoExtraSchema: undefined,
    showKindSelector: false,
    kind: 'persistent',
    entity: 'desktops',
    preview: 'desktop-card',
    context: 'new-desktop',
    alwaysShowConfiguration: false,
    showBastionConfig: false,
    showCustomDomains: false,
    showDiskSize: false,
    showPeripherals: true,
    summary: undefined,
    defaults: undefined,
    image: undefined,
    imageDomainId: undefined,
    imagePersistOnSave: true,
    imageAllowUpload: true
  }
)

const emit = defineEmits<{
  'update:image': [image: DomainImageOutput & { file?: DomainImageFile }]
  'update:kind': [kind: 'persistent' | 'nonpersistent']
}>()

const infoRef = ref<InstanceType<typeof DomainInfoSection> | null>(null)
const configRef = ref<InstanceType<typeof DomainConfigurationSection> | null>(null)

// Held here so the card is only written on submit, like every other field.
const selectedImage = ref<DomainImageOutput | undefined>(props.image)
const pendingImageFile = ref<DomainImageFile | undefined>(undefined)
const showChangeImageModal = ref(false)

watch(
  () => props.image,
  (image) => {
    selectedImage.value = image
    pendingImageFile.value = undefined
  },
  { immediate: true }
)

function handleImageSelected(image: DomainImageOutput & { file?: DomainImageFile }) {
  selectedImage.value = image
  pendingImageFile.value = image.file
  emit('update:image', image)
}

const imageIsDirty = computed(
  () =>
    !!pendingImageFile.value ||
    selectedImage.value?.id !== props.image?.id ||
    selectedImage.value?.type !== props.image?.type
)

const areFormsValid = computed(
  () => (infoRef.value?.isValid ?? false) && (configRef.value?.isValid ?? true)
)

/** Drives the restore button: access and hardware only. */
const configurationIsDirty = computed(() => !!configRef.value?.isDirty)

/** Everything the future unsaved-changes guard has to watch. */
const isDirty = computed(
  () => configurationIsDirty.value || !!infoRef.value?.isDirty || imageIsDirty.value
)

const getFormData = (): DomainConfigurationPanelData => {
  const { name, description, ...extra } = infoRef.value?.getFormData() ?? {
    name: '',
    description: ''
  }
  const configuration = configRef.value?.getFormData()

  return {
    name,
    description,
    extra,
    kind: props.kind === 'nonpersistent' ? 'nonpersistent' : 'persistent',
    access: configuration?.access,
    hardware: configuration?.hardware,
    image: selectedImage.value,
    imageFile: pendingImageFile.value
  }
}

defineExpose({
  getFormData,
  areFormsValid,
  configurationIsDirty,
  isDirty,
  /** Restores access + hardware only — never name, description or image. */
  reset: () => configRef.value?.reset(),
  openConfiguration: () => configRef.value?.open()
})
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :domain-id="imageDomainId"
    :current-image="selectedImage"
    :persist-on-save="imagePersistOnSave"
    :allow-upload="imageAllowUpload"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <div class="flex flex-col gap-10">
    <DomainInfoSection
      ref="infoRef"
      :loading="loading"
      :source="info"
      :extra-defaults="infoExtraDefaults"
      :extra-schema="infoExtraSchema"
      :image-url="selectedImage?.url || ''"
      :template-id="templateId"
      :show-kind-selector="showKindSelector"
      :kind="kind"
      :entity="entity"
      :preview="preview"
      @change-image="showChangeImageModal = true"
      @update:kind="emit('update:kind', $event)"
    >
      <template #extra="slotProps">
        <slot name="info-extra" v-bind="slotProps" />
      </template>
    </DomainInfoSection>

    <DomainConfigurationSection
      ref="configRef"
      :template-id="templateId"
      :desktop-id="desktopId"
      :loading="loading"
      :always-open="alwaysShowConfiguration"
      :show-bastion-config="showBastionConfig"
      :show-custom-domains="showCustomDomains"
      :show-disk-size="showDiskSize"
      :show-peripherals="showPeripherals"
      :summary="summary"
      :defaults="defaults"
      :kind="kind"
      :entity="entity"
      :context="context"
    />
  </div>
</template>
