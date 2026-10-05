<script setup lang="ts">
import { computed } from 'vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'

interface Props {
  label: string
  value: string
  subLabel?: string | undefined
  avatar?: string | undefined
  icon?: string | undefined
  checked?: boolean
  disabled?: boolean
  selectable?: boolean // When false the row cannot be toggled and shows no +/- indicator.
}

const props = withDefaults(defineProps<Props>(), {
  subLabel: undefined,
  avatar: undefined,
  icon: undefined,
  checked: false,
  disabled: false,
  selectable: true
})

const emit = defineEmits<{ 'update:checked': [value: boolean] }>()

const initials = computed(() =>
  props.label
    .split(' ')
    .map((word) => word[0])
    .join('')
)

const interactive = computed(() => props.selectable && !props.disabled)

const toggle = () => {
  if (!interactive.value) return
  emit('update:checked', !props.checked)
}
</script>

<template>
  <div
    :class="
      cn(
        'flex w-full min-h-10 select-none flex-row items-center gap-2 rounded-md px-2 py-1.5 font-medium text-gray-warm-700',
        props.disabled && 'cursor-not-allowed opacity-60',
        interactive &&
          'cursor-pointer hover:bg-gray-warm-50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand',
        props.checked && 'bg-brand-100 hover:bg-brand-200'
      )
    "
    role="option"
    :aria-selected="props.checked"
    :aria-disabled="props.disabled || undefined"
    :data-value="props.value"
    :tabindex="interactive ? 0 : undefined"
    @click="toggle"
    @keydown.enter.self.prevent="toggle"
    @keydown.space.self.prevent="toggle"
  >
    <Button
      v-if="props.selectable"
      as="span"
      aria-hidden="true"
      :icon="props.checked ? 'minus' : 'plus'"
      :hierarchy="props.checked ? 'secondary-destructive' : 'secondary-color'"
      size="sm"
      icon-size="sm"
      class="shrink-0 p-1.5"
      data-slot="toggle-button"
    />

    <Icon v-if="props.icon !== undefined" :name="props.icon" size="md" class="shrink-0" />
    <Avatar v-if="props.avatar !== undefined" size="xs" class="shrink-0">
      <AvatarImage :src="props.avatar" :alt="props.label" />
      <AvatarFallback>{{ initials }}</AvatarFallback>
    </Avatar>

    <div class="flex min-w-0 flex-1 flex-col">
      <span class="truncate font-semibold">{{ props.label }}</span>
      <span v-if="props.subLabel" class="truncate text-sm font-normal text-gray-warm-600">
        {{ props.subLabel }}
      </span>
    </div>

    <div v-if="$slots.actions" class="ml-auto flex shrink-0 items-center">
      <slot name="actions" />
    </div>
  </div>
</template>
