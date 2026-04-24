<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Icon } from '@/components/icon'
// import { type MultiSelectTagItemType as Tag } from '.'

interface Props {
  avatar?: string | undefined
  icon?: string | undefined
  id: string
  label: string
  subLabel?: string | undefined
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<(e: 'remove-tag', id: string) => void>()
</script>

<template>
  <div
    class="w-full flex flex-row gap-2 justify-start items-center hover:bg-base-menu-hover p-2 rounded-md h-10 select-none text-gray-warm-700 font-medium"
  >
    <Icon v-if="props.icon !== undefined" :name="props.icon" size="md" class="shrink-0" />
    <Avatar v-if="props.avatar !== undefined">
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
    <span class="text-nowrap text-ellipsis overflow-hidden">
      {{ props.label }}
    </span>

    <span v-if="props.subLabel" class="text-gray-warm-600 font-normal">
      {{ props.subLabel }}
    </span>

    <Button
      size="sm"
      hierarchy="link-color"
      icon="trash-04"
      class="ml-auto"
      @click="() => emit('remove-tag', props.id)"
    />
  </div>
</template>
