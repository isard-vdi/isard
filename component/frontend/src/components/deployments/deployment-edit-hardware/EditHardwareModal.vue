<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CreateDesktopRequest } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import { Modal } from '@/components/modal'
import DomainConfigurationSection, {
  type DomainConfigurationDefaults
} from '@/components/domain/DomainConfigurationSection.vue'
import type { AccessFormData, HardwareFormData } from '@/lib/domainPayload'
import type { LimitedHardware } from '@/lib/hardwareLimits'
import { selectedViewerKeys } from '@/lib/viewers'

const { t } = useI18n()

type DesktopData = CreateDesktopRequest & {
  limited_hardware?: LimitedHardware | null
  removed_viewers?: string[] | null
}

interface Props {
  open?: boolean
  data: DesktopData
  original?: DesktopData | null
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  original: null
})

const emit = defineEmits<{
  close: []
  submit: [{ access: AccessFormData | undefined; hardware: HardwareFormData | undefined }]
}>()

const desktopData = ref(props.data)

// There is no desktop or template to read from yet, so the sub-forms are seeded
// from the deployment entry the parent is building.
const toConfigurationDefaults = (desktop: DesktopData): DomainConfigurationDefaults => ({
  access: {
    credentials: {
      username: desktop.guest_properties?.credentials?.username ?? '',
      password: desktop.guest_properties?.credentials?.password ?? ''
    },
    fullscreen: desktop.guest_properties?.fullscreen,
    viewers: selectedViewerKeys(desktop.guest_properties?.viewers)
  },
  hardware: {
    vcpus: desktop.hardware?.vcpus ?? undefined,
    memory: desktop.hardware?.memory ?? undefined,
    diskBus: desktop.hardware?.disk_bus ?? undefined,
    videos: desktop.hardware?.videos?.[0],
    bootOrder: desktop.hardware?.boot_order?.[0],
    isos: desktop.hardware?.isos?.map((iso) => iso.id),
    floppies: desktop.hardware?.floppies?.map((floppy) => floppy.id),
    interfaces: desktop.hardware?.interfaces ?? undefined,
    reservables: { vgpus: desktop.reservables?.vgpus ?? [] }
  }
})

const defaults = computed(() => toConfigurationDefaults(desktopData.value))

const original = computed(() =>
  props.original ? toConfigurationDefaults(props.original) : undefined
)

const configurationRef = ref<InstanceType<typeof DomainConfigurationSection> | null>(null)
const isValid = computed(() => configurationRef.value?.isValid ?? false)

const submitButtonLoading = ref(false)

const handleSubmit = () => {
  if (!isValid.value || !configurationRef.value) return
  submitButtonLoading.value = true

  emit('submit', configurationRef.value.getFormData())

  submitButtonLoading.value = false
}
</script>

<template>
  <Modal
    :open="props.open"
    size="7xl"
    _class="h-full"
    hide-title
    :title="
      t('components.deployments.form-update-hardware-modal.title', {
        'desktop-name': desktopData.name
      })
    "
    :description="
      t('components.deployments.form-update-hardware-modal.description', {
        'desktop-name': desktopData.name
      })
    "
    @close="emit('close')"
  >
    <template #default>
      <div class="px-8 py-4">
        <DomainConfigurationSection
          ref="configurationRef"
          always-open
          context="deployment-desktop"
          kind="deployment"
          :defaults="defaults"
          :original="original"
          :limited-hardware="desktopData.limited_hardware"
          :initial-removed-viewers="desktopData.removed_viewers ?? undefined"
        />
      </div>
    </template>

    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.deployments.form-update-hardware-modal.cancel') }}
      </Button>
      <Button
        hierarchy="primary"
        :disabled="!isValid || submitButtonLoading"
        :icon="submitButtonLoading ? 'loading-02' : undefined"
        icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
        @click="handleSubmit"
      >
        {{ t('components.deployments.form-update-hardware-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
