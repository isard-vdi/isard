<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import { AlertModal, Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'

import StorageOptionsPanel from './StorageOptionsPanel.vue'

interface AdvancedOption {
  id: string
  label: string
  description: string
  icon: string
  component: Component
}

interface Props {
  open: boolean
  desktop?: UserDesktop
}

const props = withDefaults(defineProps<Props>(), {
  desktop: undefined
})

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()

const options = computed<AdvancedOption[]>(() => [
  {
    id: 'storage',
    label: t('components.desktops.advanced-options-modal.options.storage.label'),
    description: t('components.desktops.advanced-options-modal.options.storage.description'),
    icon: 'hard-drive',
    component: StorageOptionsPanel
  }
])

const activeOption = ref<string>(options.value[0].id)

const errorModal = ref<{ description: string } | null>(null)

watch(
  () => props.open,
  (open) => {
    if (!open) {
      errorModal.value = null
      return
    }
    activeOption.value = options.value[0].id
  }
)
</script>

<template>
  <Modal
    :open="props.open"
    size="3xl"
    :title="t('components.desktops.advanced-options-modal.title')"
    @close="emit('close')"
  >
    <Tabs
      v-model="activeOption"
      orientation="vertical"
      class="flex gap-5 bg-base-white p-4 rounded-lg border border-gray-warm-300 h-full"
    >
      <TabsList
        :aria-label="t('components.desktops.advanced-options-modal.title')"
        class="flex-col items-stretch gap-1 w-56 shrink-0 self-start"
      >
        <TabsTrigger
          v-for="option in options"
          :key="option.id"
          :value="option.id"
          class="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-sm text-start font-medium text-gray-warm-700 cursor-pointer transition-colors hover:bg-gray-warm-200 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand data-[state=active]:bg-brand-100 data-[state=active]:text-brand-700 data-[state=active]:hover:bg-brand-200"
        >
          <Icon :name="option.icon" size="md" stroke-color="currentColor" class="shrink-0" />
          <span class="min-w-0 truncate">{{ option.label }}</span>
          <Icon
            v-if="activeOption === option.id"
            name="chevron-right"
            size="md"
            stroke-color="currentColor"
            class="ml-auto shrink-0"
          />
        </TabsTrigger>
      </TabsList>

      <Separator orientation="vertical" class="h-auto self-stretch" />

      <TabsContent
        v-for="option in options"
        :key="option.id"
        :value="option.id"
        class="mt-0 flex-1 min-w-0 h-104 max-h-[60vh] overflow-y-auto pr-1"
      >
        <h3 class="text-gray-warm-900 text-md font-semibold">{{ option.label }}</h3>
        <p class="text-gray-warm-600 text-sm mt-1">{{ option.description }}</p>
        <component
          :is="option.component"
          :desktop="props.desktop"
          class="mt-5"
          @error="(msg: string) => (errorModal = { description: msg })"
        />
      </TabsContent>
    </Tabs>
  </Modal>

  <AlertModal
    v-if="errorModal"
    :open="!!errorModal"
    level="danger"
    size="md"
    :title="t('components.desktops.advanced-options-modal.error.title')"
    :description="errorModal.description"
    @close="errorModal = null"
  >
    <template #footer>
      <Button hierarchy="primary" @click="errorModal = null">
        {{ t('components.desktops.advanced-options-modal.error.close') }}
      </Button>
    </template>
  </AlertModal>
</template>
