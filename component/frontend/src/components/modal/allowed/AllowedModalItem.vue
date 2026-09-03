<script setup lang="ts">
import { computed } from 'vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'

interface Props {
  label: string
  value: string
  subLabel?: string | undefined
  avatar?: string | undefined
  icon?: string | undefined
  checked?: boolean | 'indeterminate'
  active?: boolean
  disabled?: boolean
  selectable?: boolean // When false the row has no checkbox and can only be activated.
}

const props = withDefaults(defineProps<Props>(), {
  subLabel: undefined,
  avatar: undefined,
  icon: undefined,
  checked: false,
  active: false,
  disabled: false,
  selectable: true
})

const emit = defineEmits<{
  (e: 'update:checked', value: boolean): void
  (e: 'select'): void
}>()

const initials = computed(() =>
  props.label
    .split(' ')
    .map((word) => word[0])
    .join('')
)

const toggle = () => {
  if (props.disabled) return
  emit('update:checked', props.checked !== true)
}

const select = () => {
  if (props.disabled) return
  emit('select')
}
</script>

<template>
  <div
    :class="
      cn(
        'flex w-full min-h-10 select-none flex-row items-center gap-2 rounded-md px-2 py-1.5 font-medium text-gray-warm-700',
        props.disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-gray-warm-50',
        props.active && 'bg-brand-100 hover:bg-brand-200'
      )
    "
    role="option"
    :aria-selected="props.checked === true"
    :data-value="props.value"
    :data-active="props.active || undefined"
    @click="select"
  >
    <span v-if="props.selectable" class="flex shrink-0 items-center" @click.stop>
      <Checkbox
        :model-value="props.checked"
        :indeterminate="props.checked === 'indeterminate'"
        :disabled="props.disabled"
        :aria-label="props.label"
        size="md"
        class="bg-base-white"
        @update:model-value="toggle"
      />
    </span>

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
