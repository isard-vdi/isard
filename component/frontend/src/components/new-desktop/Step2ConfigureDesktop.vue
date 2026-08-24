<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getTemplateDetailsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'
import DomainConfigurationPanel, {
  type DomainConfigurationPanelData
} from '@/components/domain/DomainConfigurationPanel.vue'

interface Template {
  id: string
  image?: DomainImageOutput
}

const props = defineProps<{
  selectedTemplate: Template
}>()

const emit = defineEmits<{
  submit: [data: DomainConfigurationPanelData]
}>()

const { isPending: templateLoading, data: templateData } = useQuery({
  ...getTemplateDetailsOptions({
    path: {
      template_id: props.selectedTemplate?.id || ''
    }
  }),
  enabled: computed(() => props.selectedTemplate !== null)
})

const panelRef = ref<InstanceType<typeof DomainConfigurationPanel> | null>(null)
const desktopKind = ref<'persistent' | 'nonpersistent'>('persistent')

// The summary types its credentials as optional strings; the template response
// returns nullable ones. No floppies: template details does not report them,
// unlike the desktop endpoint.
const summary = computed(() => ({
  credentials: {
    username: templateData.value?.credentials?.username ?? undefined,
    password: templateData.value?.credentials?.password ?? undefined
  },
  viewers: templateData.value?.viewers ?? [],
  fullscreen: templateData.value?.fullscreen,
  vcpu: templateData.value?.vcpu,
  memory: templateData.value?.memory,
  diskBus: templateData.value?.disk_bus?.name,
  videos: templateData.value?.videos?.map((video) => video.name),
  interfaces: templateData.value?.interfaces?.map((iface) => iface.name),
  bootOrder: templateData.value?.boot_order?.map((boot) => boot.name),
  isos: templateData.value?.isos?.map((iso) => iso.name),
  vgpus: templateData.value?.reservables?.vgpus
}))

const areFormsValid = computed(() => panelRef.value?.areFormsValid ?? false)

// The kind selector lives here, so the panel alone does not tell the whole story.
const isDirty = computed(() => !!panelRef.value?.isDirty || desktopKind.value !== 'persistent')

const handleSubmit = () => {
  if (!areFormsValid.value || !panelRef.value) return

  emit('submit', panelRef.value.getFormData())
}

defineExpose({
  handleSubmit,
  areFormsValid,
  isDirty
})
</script>

<template>
  <DomainConfigurationPanel
    ref="panelRef"
    :template-id="selectedTemplate?.id"
    :loading="templateLoading"
    :info="templateData"
    show-kind-selector
    :kind="desktopKind"
    :image="selectedTemplate?.image"
    :summary="summary"
    context="new-desktop"
    @update:kind="desktopKind = $event"
  />
</template>
