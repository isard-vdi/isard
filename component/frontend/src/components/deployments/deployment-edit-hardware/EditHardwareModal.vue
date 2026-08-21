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

interface Props {
  open?: boolean
  data: CreateDesktopRequest & { limited_hardware?: LimitedHardware | null }
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
  submit: [{ access: AccessFormData | undefined; hardware: HardwareFormData | undefined }]
}>()

const desktopData = ref(props.data)

const selectedViewers = computed<string[]>(() =>
  selectedViewerKeys(desktopData.value.guest_properties?.viewers)
)

// There is no desktop or template to read from yet, so the sub-forms are seeded
// from the deployment entry the parent is building.
const defaults = computed<DomainConfigurationDefaults>(() => ({
  access: {
    credentials: {
      username: desktopData.value.guest_properties?.credentials?.username ?? '',
      password: desktopData.value.guest_properties?.credentials?.password ?? ''
    },
    fullscreen: desktopData.value.guest_properties?.fullscreen,
    viewers: selectedViewers.value
  },
  hardware: {
    vcpus: desktopData.value.hardware?.vcpus ?? undefined,
    memory: desktopData.value.hardware?.memory ?? undefined,
    diskBus: desktopData.value.hardware?.disk_bus ?? undefined,
    videos: desktopData.value.hardware?.videos?.[0],
    bootOrder: desktopData.value.hardware?.boot_order?.[0],
    isos: desktopData.value.hardware?.isos?.map((iso) => iso.id),
    floppies: desktopData.value.hardware?.floppies?.map((floppy) => floppy.id),
    interfaces: desktopData.value.hardware?.interfaces ?? undefined,
    reservables: { vgpus: desktopData.value.reservables?.vgpus ?? [] }
  }
}))

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
          :defaults="defaults"
          :limited-hardware="desktopData.limited_hardware"
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
