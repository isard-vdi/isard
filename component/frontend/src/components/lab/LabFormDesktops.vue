<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import Button from '@/components/ui/button/Button.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import DesktopListItem from '@/components/desktop-list-item/DesktopListItem.vue'

import { getAllTemplatesOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  desktops: Record<string, unknown>[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false
})

const canAddNewDesktop = computed(() => {
  return props.desktops.every((desktop) => desktop.template !== null)
})

const emit = defineEmits(['update:desktops', 'add-desktop', 'update-desktop', 'delete-desktop'])

const { t } = useI18n()

const activeTemplateTab = ref('shared')
const templateSearchTerm = ref('')

const {
  data: templatesData,
  isPending: isTemplatesLoading,
  isError: isTemplatesError
} = useQuery(getAllTemplatesOptions())

const filteredTemplates = computed(() => {
  if (!templatesData.value?.templates) return []

  const tabFiltered = templatesData.value.templates.filter((template) => {
    if (activeTemplateTab.value === 'my') {
      return template.user === 'current-user'
    } else {
      return true
    }
  })

  if (!templateSearchTerm.value) return tabFiltered

  return tabFiltered.filter(
    (template) =>
      template.name.toLowerCase().includes(templateSearchTerm.value.toLowerCase()) ||
      (template.description != null &&
        template.description.toLowerCase().includes(templateSearchTerm.value.toLowerCase()))
  )
})

const addDesktop = () => {
  emit('add-desktop')
}

const updateDesktop = (id: number, key: string, value: unknown) => {
  emit('update-desktop', id, key, value)
}

const deleteDesktop = (id: number) => {
  emit('delete-desktop', id)
}
</script>

<template>
  <div class="gap-8 py-8 items-center">
    <h2 class="text-lg font-semibold text-gray-warm-900 mb-2">
      {{ t('views.form-lab.desktops.title') }}
    </h2>
    <p class="text-sm text-gray-600 mb-4">
      {{ t('views.form-lab.desktops.info') }}
    </p>

    <div class="flex justify-center">
      <div
        v-if="desktops.length === 0"
        class="text-center p-8 w-120 lg:w-256 border border-dashed border-gray-warm-300 rounded-lg"
      >
        <p class="text-gray-warm-600">{{ t('views.form-lab.desktops.no-desktops') }}</p>
      </div>

      <div v-else class="flex flex-col items-center">
        <DesktopListItem
          v-for="(desktop, index) in desktops"
          :key="desktop.id || index"
          :number="index + 1"
          :name="desktop.name"
          :description="desktop.description"
          :image="desktop.image"
          :hardware="desktop.hardware"
          :selected-template="desktop.template"
          :templates="filteredTemplates"
          :is-templates-loading="isTemplatesLoading"
          :is-templates-error="isTemplatesError"
          :template-search-term="templateSearchTerm"
          :active-template-tab="activeTemplateTab"
          :disabled="disabled"
          @update:name="(value) => updateDesktop(desktop.id, 'name', value)"
          @update:description="(value) => updateDesktop(desktop.id, 'description', value)"
          @update:image="(value) => updateDesktop(desktop.id, 'image', value)"
          @update:hardware="(value) => updateDesktop(desktop.id, 'hardware', value)"
          @update:guest_properties="(value) => updateDesktop(desktop.id, 'guest_properties', value)"
          @update:template="(value) => updateDesktop(desktop.id, 'template', value)"
          @update:template-search-term="(value) => (templateSearchTerm = value)"
          @update:active-template-tab="(value) => (activeTemplateTab = value)"
          @delete="deleteDesktop(desktop.id)"
        />
      </div>
    </div>

    <div v-if="!disabled" class="m-6 flex justify-center items-center">
      <Separator class="w-full mr-6" />
      <Button
        type="button"
        hierarchy="secondary-gray"
        :disabled="!canAddNewDesktop"
        :title="!canAddNewDesktop ? t('views.form-lab.desktops.complete-templates-first') : ''"
        @click="addDesktop"
      >
        {{ t('views.form-lab.desktops.add') }}
      </Button>
      <Separator class="w-full ml-6" />
    </div>
  </div>
</template>
