<script setup lang="ts">
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  title?: string
  description?: string
  showCloseButton?: boolean
  closeButtonColor?: string
  open?: boolean
  class?: HTMLAttributes['class']
  closeOnBackdropClick?: boolean
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | '5xl' | '6xl' | '7xl' | 'full'
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  showCloseButton: true,
  closeButtonColor: 'secondary-2-500',
  open: false,
  class: '',
  closeOnBackdropClick: true,
  size: 'md'
})

const emit = defineEmits(['close'])

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
  '6xl': 'max-w-6xl',
  '7xl': 'max-w-7xl',
  full: 'max-w-[95vw]'
}
</script>

<template>
  <Dialog :open="props.open" @update:open="(v) => !v && emit('close')">
    <DialogContent
      :class="
        cn(
          'bg-base-background shadow-md max-h-[90vh] flex flex-col p-0 w-[95vw]',
          sizeClasses[props.size],
          props.class
        )
      "
      @pointer-down-outside="
        (event: Event) => {
          if (props.closeOnBackdropClick) {
            emit('close')
          } else {
            event.preventDefault()
          }
        }
      "
      @escape-key-down="emit('close')"
    >
      <slot name="image" />
      <DialogHeader class="flex text-start justify-between items-start px-6 pt-6 shrink-0">
        <div>
          <DialogTitle v-if="props.title" class="text-gray-warm-900 text-lg">
            {{ props.title }}
          </DialogTitle>
          <DialogDescription v-if="props.description" class="text-gray-warm-600 text-sm mt-2">
            {{ props.description }}
          </DialogDescription>
        </div>
        <Button
          v-if="props.showCloseButton"
          hierarchy="link-color"
          class="absolute top-3 right-3 z-20 cursor-pointer"
          @click="emit('close')"
        >
          <Icon name="x" :stroke-color="props.closeButtonColor" size="md" />
        </Button>
      </DialogHeader>

      <div class="px-6 overflow-y-auto">
        <slot></slot>
      </div>

      <DialogFooter class="shrink-0 sm:justify-center pb-4 px-6 mt-auto">
        <slot name="footer"></slot>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
