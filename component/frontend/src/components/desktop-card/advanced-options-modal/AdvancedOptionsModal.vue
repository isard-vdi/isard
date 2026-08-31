<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEventListener } from '@vueuse/core'

import type { ApiSchemasDomainsDesktopsUserDesktop as UserDesktop } from '@/gen/oas/apiv4'

import { useAuthStore } from '@/stores/auth'

import { Modal } from '@/components/modal'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'

import { advancedOptionsForRole } from './options'

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
const authStore = useAuthStore()

const options = computed(() =>
  advancedOptionsForRole(authStore.user?.role_id).map((option) => ({
    ...option,
    label: t(option.labelKey),
    description: t(option.descriptionKey)
  }))
)

const activeOption = ref<string>(options.value[0]?.id ?? '')

const errorMessage = ref<string | null>(null)

// The alert lives in the panel that raised it, so it must not survive a
// jump to another option.
const ERROR_ALERT_ID = 'advanced-options-error'
watch(activeOption, () => (errorMessage.value = null))

const showError = (message: string) => {
  errorMessage.value = message
  nextTick(() => {
    document.getElementById(ERROR_ALERT_ID)?.scrollIntoView?.({ block: 'nearest' })
  })
}

const showId = ref(false)
useEventListener(window, 'keydown', (e: KeyboardEvent) => {
  if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'i') {
    showId.value = !showId.value
  }
})

watch(
  () => props.open,
  (open) => {
    if (!open) {
      errorMessage.value = null
      showId.value = false
      return
    }
    errorMessage.value = null
    activeOption.value = options.value[0]?.id ?? ''
  }
)
</script>

<template>
  <Modal
    :open="props.open"
    size="3xl"
    :title="t('components.desktops.advanced-options-modal.title')"
    :description="
      t('components.desktops.advanced-options-modal.subtitle', {
        name: (props.desktop?.name ?? '').toUpperCase()
      })
    "
    @close="emit('close')"
  >
    <Tabs
      v-if="options.length > 0"
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
          class="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-sm text-start font-medium text-gray-warm-700 cursor-pointer transition-colors hover:bg-gray-warm-200 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand data-[state=active]:bg-brand-100 data-[state=active]:font-bold data-[state=active]:text-brand-700 data-[state=active]:hover:bg-brand-200"
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
        class="mt-0 flex-1 min-w-0 h-114 max-h-[60vh] overflow-y-auto px-1.5"
      >
        <h3 class="text-gray-warm-900 text-md font-semibold">{{ option.label }}</h3>
        <p class="text-gray-warm-600 text-sm mt-1">{{ option.description }}</p>
        <component
          :is="option.component"
          :desktop="props.desktop"
          :show-id="showId"
          class="mt-2"
          @error="showError"
          @success="emit('close')"
        />
        <Alert v-if="errorMessage" :id="ERROR_ALERT_ID" variant="destructive" class="mt-4">
          <Icon name="alert-circle" size="md" stroke-color="error-700" />
          <AlertTitle class="font-semibold text-error-700">
            {{ t('components.desktops.advanced-options-modal.error.title') }}
          </AlertTitle>
          <AlertDescription class="text-gray-warm-700">{{ errorMessage }}</AlertDescription>
        </Alert>
      </TabsContent>
    </Tabs>
  </Modal>
</template>
