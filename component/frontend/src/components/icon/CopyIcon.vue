<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import { Icon, iconVariants } from '.'
import { type Props as IconProps } from '@/components/icon/Icon.vue'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const { t } = useI18n()

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

const tooltip = computed(() =>
  disabled.value ? t('common.actions.copied') : t('common.actions.copy')
)
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
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
    </TooltipTrigger>
    <TooltipContent :title="tooltip" />
  </Tooltip>
</template>
