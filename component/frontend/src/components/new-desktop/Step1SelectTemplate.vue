<script setup lang="ts">
import { ref } from 'vue'
import { useMutation } from '@tanstack/vue-query'
import TemplatesList from '@/components/templates/TemplatesList.vue'
import { DomainInfoModal } from '@/components/desktops'
import { getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet } from '@/gen/oas/apiv4/'

interface Props {
  selectedId?: string
}

const props = defineProps<Props>()

interface Template {
  id: string
  image?: { url: string }
}

const emit = defineEmits<{
  selectTemplate: [template: Template]
}>()

const handleRowClick = (template: Template) => {
  emit('selectTemplate', template)
}

// Template Info Modal
const showTemplateInfoModal = ref(false)
const {
  mutate: fetchAndOpenTemplateInfoModal,
  isPending: fetchTemplateDetailsIsPending,
  isError: fetchTemplateDetailsIsError,
  error: fetchTemplateDetailsError,
  data: templateDetails,
  variables: templateDetailsDesktopId,
  reset: resetTemplateDetails
} = useMutation({
  mutationFn: async (templateId: string) => {
    const { data } = await getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet({
      path: {
        template_id: templateId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess: () => {
    showTemplateInfoModal.value = true
  }
})
</script>

<template>
  <DomainInfoModal
    :open="showTemplateInfoModal"
    :domain-id="templateDetailsDesktopId"
    :name="templateDetails?.name || ''"
    :description="templateDetails?.description"
    :status="templateDetails?.status"
    :ip="templateDetails?.ip"
    :vcpu="templateDetails?.vcpu"
    :ram="templateDetails?.memory"
    :boot-order="templateDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="templateDetails?.disk_bus"
    :vga="templateDetails?.videos.map((vga) => vga.name)"
    :viewers="templateDetails?.viewers"
    :isos="templateDetails?.isos?.map((iso) => iso.name)"
    :floppies="templateDetails?.floppies?.map((floppy) => floppy.name)"
    :reservables="templateDetails?.reservables?.vgpus"
    :kind="'template'"
    @close="
      () => {
        showTemplateInfoModal = false
        resetTemplateDetails()
      }
    "
  />
  <TemplatesList
    active-template-tab="user"
    :selectable="true"
    @row-click="handleRowClick"
    @show-info-modal="fetchAndOpenTemplateInfoModal"
    :selected-id="props.selectedId"
  />
</template>
