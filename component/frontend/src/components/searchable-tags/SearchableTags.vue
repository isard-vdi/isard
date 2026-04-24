<script setup lang="ts">
import {
  ListboxContent,
  ListboxFilter,
  ListboxItem,
  ListboxItemIndicator,
  ListboxRoot,
  useFilter
} from 'reka-ui'
import { computed, ref, watch } from 'vue'
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  TagsInput,
  TagsInputInput,
  TagsInputItem,
  TagsInputItemDelete,
  TagsInputItemText
} from '@/components/ui/tags-input'
import { Icon } from '@/components/icon'

// https://www.figma.com/design/B0Hv6jY90m5K6AtGwACAGo/ISARD-Design-system-Cliente--Copy-?node-id=3281-377673&t=K43HTMUALe5MqFog-4

// TODO: should be like https://www.figma.com/design/B0Hv6jY90m5K6AtGwACAGo/ISARD-Design-system-Cliente--Copy-?node-id=9016-17314&m=dev

interface Tag {
  value: string
  label: string
}

interface Props {
  modelValue?: string[]
  tags: Tag[]
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  tags: () => [] as Tag[],
  placeholder: ''
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const open = ref(false)
const searchTerm = ref('')

// Watch search term to open popover when typing
watch(searchTerm, (f) => {
  if (f) {
    open.value = true
  }
})

const { contains } = useFilter({ sensitivity: 'base' })

const filteredTags = computed(() =>
  searchTerm.value === ''
    ? props.tags
    : props.tags.filter((option) => contains(option.label, searchTerm.value))
)
</script>

<template>
  <Popover v-model:open="open">
    <ListboxRoot
      :model-value="props.modelValue"
      highlight-on-hover
      multiple
      @update:model-value="emit('update:modelValue', $event)"
    >
      <PopoverAnchor class="inline-flex w-full">
        <TagsInput
          :model-value="props.modelValue"
          class="flex items-center justify-between h-10 w-full px-[14px] py-[10px] rounded-md border border-gray-warm-300 bg-base-white text-md leading-md text-gray-warm-900 font-medium gap-2 outline-hidden transition-colors focus-within:border-gray-warm-700 focus-within:ring-3 focus-within:ring-brand focus-within:shadow-none hover:border-gray-warm-400"
          @click="open = true"
        >
          <TagsInputItem
            v-for="item in props.modelValue"
            :key="item.toString()"
            :value="item.toString()"
          >
            <TagsInputItemText>
              {{ props.tags.find((tag) => tag.value === item.toString())?.label }}
            </TagsInputItemText>
            <TagsInputItemDelete
              @click.stop="
                emit(
                  'update:modelValue',
                  props.modelValue.filter((v) => v !== item)
                )
              "
            />
          </TagsInputItem>

          <ListboxFilter v-model="searchTerm" as-child>
            <TagsInputInput
              :placeholder="props.placeholder"
              class="flex-1 min-w-[120px] shadow-none p-0 border-none focus-visible:ring-0 focus-visible:shadow-none outline-none bg-transparent text-md placeholder:text-gray-warm-500 placeholder:font-regular"
              @keydown.enter.prevent
              @keydown.down="open = true"
              @focus="open = true"
            />
          </ListboxFilter>

          <PopoverTrigger as-child>
            <Icon
              name="chevron-down"
              stroke-color="gray-warm-500"
              class="shrink-0 ml-auto pointer-events-none"
            />
          </PopoverTrigger>
        </TagsInput>
      </PopoverAnchor>

      <PopoverContent class="p-1 w-(--reka-popper-anchor-width)" @open-auto-focus.prevent>
        <ListboxContent
          class="max-h-[200px] scroll-py-1 overflow-x-hidden overflow-y-auto empty:after:content-['No_options'] empty:p-1 empty:after:block text-md text-gray-warm-900"
          tabindex="0"
        >
          <ListboxItem
            v-for="tag in filteredTags"
            :key="tag.value"
            class="data-[highlighted]:bg-brand-100 data-[highlighted]:text-accent-foreground relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
            :value="tag.value"
            @select="
              () => {
                searchTerm = ''
              }
            "
          >
            <span>{{ tag.label }}</span>

            <ListboxItemIndicator class="ml-auto inline-flex items-center justify-center">
              <Icon name="check" stroke-color="gray-warm-500" />
            </ListboxItemIndicator>
          </ListboxItem>
        </ListboxContent>
      </PopoverContent>
    </ListboxRoot>
  </Popover>
</template>
