<script setup lang="ts">
import Modal from './Modal.vue'
import { cn } from '@/lib/utils'
import { modalVariants, type ModalVariants } from '.'
import Icon from '@/components/icon/Icon.vue'
import { computed } from 'vue'
import dotGrid from '@/assets/img/modal/dot-grid.svg?component'
import modalInfo from '@/assets/img/modal/info.svg'
import modalWarning from '@/assets/img/modal/warning.svg'
import modalDanger from '@/assets/img/modal/danger.svg'
import modalSuccess from '@/assets/img/modal/success.svg'

const levelImages: Record<string, string> = {
  info: modalInfo,
  warning: modalWarning,
  danger: modalDanger,
  success: modalSuccess
}

interface Props {
  level?: ModalVariants['level']
  title: string
  description?: string
  open?: boolean
  size?: ModalVariants['size']
  loading?: boolean
  showCloseButton?: boolean
  closeOnBackdropClick?: boolean
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  level: 'info',
  open: false,
  size: 'md',
  loading: false,
  showCloseButton: true,
  closeOnBackdropClick: true
})

const emit = defineEmits(['update:open', 'cancel'])

const handleClose = () => {
  if (props.loading) return
  emit('update:open', false)
  emit('cancel')
}

const widthClass = computed(() => {
  if (props.size === 'lg') return 'w-140'
  return 'w-96'
})
</script>

<template>
  <Modal
    :open="props.open"
    :has-image="true"
    :close-on-backdrop-click="!props.loading && props.closeOnBackdropClick"
    :show-close-button="props.showCloseButton"
    :close-button-color="'base-white'"
    :class="cn('rounded-lg', widthClass, props.class)"
    :title="props.title"
    :_description="props.description"
    @close="handleClose"
  >
    <template #image>
      <div
        :class="
          cn(
            modalVariants({ level: props.level }),
            'relative rounded-t-lg w-full h-58 overflow-hidden flex items-center justify-center'
          )
        "
      >
        <component
          :is="dotGrid"
          class="absolute left-1/2 -translate-x-1/2 opacity-50 max-w-full text-base-white"
          :style="{ maskImage: 'linear-gradient(to bottom, white 10%, transparent 100%)' }"
          aria-hidden="true"
        />
        <img
          :src="levelImages[props.level ?? 'info']"
          :alt="`${props.level} modal`"
          class="relative z-10 top-4 self-start max-w-full"
        />
      </div>
    </template>

    <template #default>
      <div v-if="props.description" class="flex items-center gap-2 whitespace-pre-line">
        <Icon v-if="props.loading" name="loading-03" size="sm" class="animate-spin" />
        <!-- TODO: use Spinner component -->
        <span class="wrap-break-word w-full">{{ props.description }}</span>
      </div>
      <slot name="description" />
    </template>

    <template #footer>
      <div class="flex w-full justify-center items-center pb-5 gap-2">
        <slot name="footer"></slot>
      </div>
    </template>
  </Modal>
</template>
