<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Icon } from '@/components/icon'
// import { type MultiSelectTagItemType as Tag } from '.'
import { Checkbox } from '@/components/ui/checkbox'

interface Props {
  label: string
  subLabel?: string | undefined
  value: string
  avatar?: string | undefined
  icon?: string | undefined
  checked?: boolean | 'indeterminate'
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  (e: 'update:checked', value: boolean | 'indeterminate'): void
}>()
</script>

<template>
  <div
    class="w-full flex flex-row gap-2 justify-start items-center hover:bg-base-menu-hover p-8 rounded-md h-10 select-none text-gray-warm-700 font-medium"
  >
    <Checkbox
      :model-value="props.checked"
      :indeterminate="props.checked === 'indeterminate'"
      size="md"
      @update:model-value="(value) => emit('update:checked', value)"
    />
    <Icon v-if="props.icon" :name="props.icon" size="md" class="shrink-0" />
    <Avatar v-if="props.avatar">
      <AvatarImage :src="props.avatar" :alt="props.label" />
      <AvatarFallback>
        {{
          props.label
            .split(' ')
            .map((n) => n[0])
            .join('')
        }}
      </AvatarFallback>
    </Avatar>
    <div class="flex flex-col overflow-hidden">
      <span class="font-semibold text-nowrap text-ellipsis overflow-hidden">
      {{ props.label }}
      </span>
      <span
      v-if="props.subLabel"
      class="text-gray-warm-600 font-normal text-sm text-nowrap text-ellipsis overflow-hidden"
      >
      {{ props.subLabel }}
      </span>
    </div>
    <slot name="actions" />
  </div>
</template>
