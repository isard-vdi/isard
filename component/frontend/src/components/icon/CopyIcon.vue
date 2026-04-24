<script setup lang="ts">
import { ref } from 'vue'

import { cn } from '@/lib/utils'

import { Icon, iconVariants } from '.'
import { type Props as IconProps } from '@/components/icon/Icon.vue'

interface Props extends Pick<IconProps, 'size' | 'alt' | 'class' | 'fillColor' | 'strokeColor'> {
  value: string
  name?: string
  successName?: string
  errorName?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: 'copy-06',
  successName: 'check',
  errorName: 'alert-triangle'
})

const iconName = ref(props.name)

const disabled = ref(false)
const copyText = (text: string) => {
  navigator.clipboard.writeText(text).then(
    () => {
      iconName.value = Math.random() < 0.001 ? 'face-smile' : props.successName
      disabled.value = true
    },
    (err) => {
      iconName.value = props.errorName
      console.error('Could not copy text: ', err)
    }
  )

  setTimeout(() => {
    iconName.value = props.name
    disabled.value = false
  }, 1000)
}
</script>

<template>
  <div :class="cn(iconVariants({ size }))">
    <Icon
      :name="iconName"
      :size="props.size"
      :alt="props.alt"
      :class="cn(props.class, 'select-none', disabled ? '' : 'cursor-pointer')"
      :fill-color="props.fillColor"
      :stroke-color="props.strokeColor"
      @click="
        () => {
          if (!disabled) {
            copyText(props.value)
          }
        }
      "
    />
  </div>
</template>
