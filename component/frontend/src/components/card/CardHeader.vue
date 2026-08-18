<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { cn } from '@/lib/utils'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import CardModal from './CardModal.vue'

const { t } = useI18n()

const props = defineProps<{
  class?: HTMLAttributes['class']
  backgroundImage?: string
  title: string
  description: string
  desktopsCount: number
  cardMenus: string[]
}>()

const showModal = ref(false)

const emit = defineEmits(['network-click', 'menu-click', 'image-click'])

watch(showModal, (val) => {
  if (val) {
    document.body.classList.add('overflow-hidden')
  } else {
    document.body.classList.remove('overflow-hidden')
  }
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') showModal.value = false
}
onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div
    :class="
      cn(
        'gap-y-1.5 p-3 rounded-t-lg flex items-end bg-cover bg-center relative',
        'h-64',
        props.class
      )
    "
    :style="
      props.backgroundImage
        ? {
            backgroundImage: `linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,0.7)), url(${props.backgroundImage})`
          }
        : {}
    "
  >
    <slot />

    <!-- Header icons/buttons -->
    <div class="absolute top-3 right-3 flex gap-2 z-10">
      <Tooltip v-if="props.cardMenus.includes('info')">
        <TooltipTrigger as-child>
          <Button
            type="button"
            class="w-9 h-9 bg-black hover:bg-brand-800 rounded-sm opacity-50 hover:opacity-100 flex items-center justify-center"
            @click="showModal = true"
          >
            <Icon name="info-circle" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.card.card-header.info')" />
      </Tooltip>
      <Tooltip v-if="props.cardMenus.includes('network')">
        <TooltipTrigger as-child>
          <Button
            type="button"
            class="w-9 h-9 bg-black hover:bg-brand-800 rounded-sm opacity-50 hover:opacity-100 flex items-center justify-center"
            @click="emit('network-click')"
          >
            <!-- TODO: network button listener -->
            <Icon name="modem-02" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.card.card-header.network')" />
      </Tooltip>
      <Tooltip v-if="props.cardMenus.includes('menu')">
        <TooltipTrigger as-child>
          <Button
            type="button"
            class="w-9 h-9 bg-black hover:bg-brand-800 rounded-sm opacity-50 hover:opacity-100 flex items-center justify-center"
            @click="emit('menu-click')"
          >
            <!-- TODO: menu button listener -->
            <Icon name="dots-vertical" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.card.card-header.menu')" />
      </Tooltip>
      <Tooltip v-if="props.cardMenus.includes('image')">
        <TooltipTrigger as-child>
          <Button
            type="button"
            class="w-9 h-9 bg-black hover:bg-brand-800 rounded-sm opacity-50 hover:opacity-100 flex items-center justify-center"
            @click="emit('image-click')"
          >
            <!-- TODO: menu button listener -->
            <Icon name="image-plus" stroke-color="base-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent :title="t('components.card.card-header.image')" />
      </Tooltip>
    </div>

    <!-- Info Modal -->
    <CardModal
      :show-modal="showModal"
      :title="title"
      :description="description"
      :desktops-count="desktopsCount"
      @close="showModal = false"
    />
  </div>
</template>
