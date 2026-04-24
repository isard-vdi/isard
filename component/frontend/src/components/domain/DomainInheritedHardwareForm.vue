<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import {
  getTemplateInfoOptions,
  getDesktopInfoApiV4ItemDesktopDesktopIdGetInfoGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  templateId?: string
  desktopId?: string
}

const props = defineProps<Props>()

const hardwareFormRef = ref<InstanceType<typeof DomainHardwareForm> | null>(null)

// Fetch template info when templateId is provided
const {
  isPending: templateLoading,
  error: templateError,
  data: templateData
} = useQuery({
  ...getTemplateInfoOptions({
    path: {
      template_id: props.templateId!
    }
  }),
  enabled: computed(() => !!props.templateId)
})

// Fetch desktop info when desktopId is provided
const {
  isPending: desktopLoading,
  error: desktopError,
  data: desktopData
} = useQuery({
  ...getDesktopInfoApiV4ItemDesktopDesktopIdGetInfoGetOptions({
    path: {
      desktop_id: props.desktopId!
    }
  }),
  enabled: computed(() => !!props.desktopId)
})

const loading = computed(() => {
  if (props.templateId) {
    return templateLoading.value
  }
  if (props.desktopId) {
    return desktopLoading.value
  }
  return false
})
const data = computed(() => desktopData.value || templateData.value)
const vcpus = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.vcpus
})

const memory = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.memory
})

const diskBus = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.disk_bus
})

const videos = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.videos[0]
})

const boots = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.boot_order[0]
})

const isos = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.isos?.map((iso) => iso.id) ?? []
})

const floppies = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.floppies
})

const vgpus = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.reservables.vgpus
})

const networks = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.hardware.interfaces
})

const limitedHardware = computed(() => {
  const source = desktopData.value || templateData.value
  return source?.limited_hardware
})

// Expose method to get form data from child component
const getFormData = () => {
  return hardwareFormRef.value?.getFormData()
}

// Expose computed values for summary display
defineExpose({
  getFormData,
  vcpus,
  memory,
  diskBus,
  videos,
  boots,
  isos,
  floppies,
  vgpus,
  networks,
  limitedHardware,
  loading
})
</script>
<template>
  <DomainHardwareForm
    ref="hardwareFormRef"
    :vcpus="vcpus"
    :memory="memory"
    :loading="loading"
    :disk-bus="diskBus"
    :videos="videos"
    :boots="boots"
    :isos="isos"
    :floppies="floppies"
    :vgpus="vgpus"
    :networks="networks"
    :limited-hardware="limitedHardware"
  />
</template>
