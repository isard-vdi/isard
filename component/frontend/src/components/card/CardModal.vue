<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { onMounted, onUnmounted } from 'vue'
import Icon from '@/components/icon/Icon.vue'
import Button from '@/components/ui/button/Button.vue'

const props = defineProps<{
  showModal: boolean
  title: string
  description: string
  desktopsCount: number
}>()

const emit = defineEmits<(e: 'close') => void>()

const { t } = useI18n()

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div
    v-if="props.showModal"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    role="dialog"
    aria-modal="true"
    @click.self="emit('close')"
  >
    <div class="flex flex-col bg-base-background shadow-lg w-[432px] h-64 rounded-lg pb-6">
      <div class="pb-5 pt-6 pr-6 pl-6 h-24 flex justify-between">
        <div class="h-18 gap-1 flex flex-col">
          <h1 class="font-bold text-lg text-gray-warm-900">
            {{ t('components.card.card-header.information') }}
          </h1>
          <p>{{ props.title }}</p>
        </div>
        <Button hierarchy="link" @click="emit('close')">
          <Icon name="x-close" stroke-color="secondary-2-500" />
        </Button>
      </div>
      <div class="flex flex-col gap-5 pr-6 pl-6 h-38">
        <div class="flex flex-col gap-4">
          <h2 class="font-bold text-sm text-gray-warm-500">
            {{ t('components.card.card-header.description') }}
          </h2>
          <p>{{ props.description }}</p>
        </div>
        <div class="flex flex-col gap-4">
          <h2 class="font-bold text-sm text-gray-warm-500">
            {{ t('components.card.card-header.desktops') }}
          </h2>
          <div class="flex flex-row gap-4 items-center">
            <Icon name="server-03" />
            <p class="font-semibold text-sm text-gray-warm-700">
              {{ props.desktopsCount }} {{ t('components.card.card-header.desktops') }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
