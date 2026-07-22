<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
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

const emit = defineEmits(['update:open', 'cancel', 'close'])

const handleClose = () => {
  if (props.loading) return
  emit('update:open', false)
  emit('cancel')
  emit('close')
}

const widthClass = computed(() => {
  if (props.size === 'lg') return 'w-140'
  return 'w-96'
})
</script>

<template>
  <AlertDialog :open="props.open" @update:open="(v) => !v && handleClose()">
    <AlertDialogContent
      :class="
        cn(
          'bg-base-background shadow-md max-h-[90vh] flex flex-col p-0 rounded-lg overflow-hidden',
          widthClass,
          props.class
        )
      "
      @escape-key-down="handleClose()"
      @pointer-down-outside="
        (event: Event) => {
          if (props.closeOnBackdropClick && !props.loading) {
            handleClose()
          } else {
            event.preventDefault()
          }
        }
      "
    >
      <div
        :class="
          cn(
            modalVariants({ level: props.level }),
            'relative w-full h-58 overflow-hidden flex items-center justify-center'
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

      <AlertDialogHeader class="flex text-start justify-between items-start px-6 pt-6 shrink-0">
        <div>
          <AlertDialogTitle v-if="props.title" class="text-gray-warm-900 text-lg">
            {{ props.title }}
          </AlertDialogTitle>
          <AlertDialogDescription v-if="props.description" class="sr-only">
            {{ props.description }}
          </AlertDialogDescription>
        </div>
        <Button
          v-if="props.showCloseButton"
          hierarchy="link-color"
          class="absolute top-3 right-3 z-20 cursor-pointer"
          @click="handleClose()"
        >
          <Icon name="x" stroke-color="base-white" size="md" />
        </Button>
      </AlertDialogHeader>

      <div class="px-6 overflow-y-auto">
        <div v-if="props.description" class="flex items-center gap-2 whitespace-pre-line">
          <Icon v-if="props.loading" name="loading-03" size="sm" class="animate-spin" />
          <span class="wrap-break-word w-full">{{ props.description }}</span>
        </div>
        <slot name="description" />
      </div>

      <AlertDialogFooter class="shrink-0 sm:justify-center pb-4 px-6 mt-auto">
        <div class="flex w-full justify-center items-center pb-5 gap-2">
          <slot name="footer"></slot>
        </div>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
