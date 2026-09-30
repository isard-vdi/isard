<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import { Comment, Fragment, Text, useAttrs, useSlots, type HTMLAttributes, type VNode } from 'vue'
import type { ButtonVariants } from '.'
import { Primitive } from 'reka-ui'
import { cn } from '@/lib/utils'
import { buttonVariants } from '.'
import { Icon, type IconVariants } from '@/components/icon'
import { injectTooltipTriggerTitle } from '@/components/ui/tooltip/context'

interface Props extends PrimitiveProps {
  hierarchy?: ButtonVariants['hierarchy']
  size?: ButtonVariants['size']
  icon?: string
  class?: HTMLAttributes['class']
  iconSize?: IconVariants['size']
  iconFillColor?: string
  iconStrokeColor?: string
  iconClass?: HTMLAttributes['class']
}

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  iconStrokeColor: 'currentColor'
})

const slots = useSlots()
const attrs = useAttrs()
const tooltipTitle = injectTooltipTriggerTitle()

function hasContent(nodes: VNode[] | undefined): boolean {
  return !!nodes?.some((node) => {
    if (node.type === Comment) return false
    if (node.type === Text) return String(node.children).trim() !== ''
    if (node.type === Fragment) return hasContent(node.children as VNode[])
    return true
  })
}

// Called from the template: slots must only be evaluated during render.
function accessibleName() {
  const explicit = attrs['aria-label'] as string | undefined
  if (explicit || attrs['aria-labelledby'] || !props.icon) return explicit
  if (hasContent(slots.default?.())) return undefined
  return tooltipTitle?.value || undefined
}
</script>

<template>
  <Primitive
    v-bind="$attrs"
    data-slot="button"
    :as="as"
    :as-child="asChild"
    :aria-label="accessibleName()"
    :class="cn(buttonVariants({ hierarchy, size }), props.class)"
  >
    <Icon
      v-if="props.icon"
      :key="props.icon"
      :name="props.icon"
      :size="props.iconSize"
      :fill-color="props.iconFillColor"
      :stroke-color="props.iconStrokeColor"
      :class="cn('shrink-0', props.iconClass)"
    />
    <slot />
  </Primitive>
</template>
