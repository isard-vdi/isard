<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ChevronDown, Search } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxTrigger,
  ComboboxList,
  ComboboxInput,
  ComboboxItem
} from '@/components/ui/combobox'
import { selectTriggerVariants } from '@/components/ui/select'
import type { VirtInstallItem } from '@/gen/oas/apiv4/types.gen'

interface Props {
  options: VirtInstallItem[]
  modelValue?: string
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
  minSearchLength?: number
  maxResults?: number
  previewCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  disabled: false,
  invalid: false,
  placeholder: '',
  minSearchLength: 1,
  maxResults: 20,
  previewCount: 10
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const open = ref(false)
const search = ref('')

watch(open, (isOpen) => {
  if (!isOpen) search.value = ''
})

const selectedOption = computed(() =>
  props.options.find((option) => option.id === props.modelValue)
)

const hasMinSearchLength = computed(() => search.value.trim().length >= props.minSearchLength)

const matchingOptions = computed(() => {
  if (!hasMinSearchLength.value) return props.options
  const term = search.value.trim().toLowerCase()
  return props.options.filter(
    (option) =>
      option.name.toLowerCase().includes(term) || (option.vers ?? '').toLowerCase().includes(term)
  )
})

const visibleLimit = computed(() =>
  hasMinSearchLength.value ? props.maxResults : props.previewCount
)
const visibleOptions = computed(() => matchingOptions.value.slice(0, visibleLimit.value))
const hiddenResultsCount = computed(
  () => matchingOptions.value.length - visibleOptions.value.length
)

const handleSelect = (value: string) => {
  emit('update:modelValue', value)
  open.value = false
}
</script>

<template>
  <Combobox
    v-model:open="open"
    :model-value="props.modelValue"
    :disabled="props.disabled"
    ignore-filter
    :reset-search-term-on-blur="false"
    :reset-search-term-on-select="false"
    @update:model-value="(value) => handleSelect(value as string)"
  >
    <ComboboxAnchor as-child class="w-full">
      <ComboboxTrigger as-child>
        <button
          type="button"
          tabindex="0"
          :class="
            cn(
              selectTriggerVariants(),
              'justify-start',
              selectedOption ? 'text-gray-warm-900' : 'text-gray-warm-500',
              props.invalid ? 'ring-3 ring-error' : ''
            )
          "
        >
          <span class="truncate">
            {{
              selectedOption
                ? selectedOption.name + (selectedOption.vers ? ` (${selectedOption.vers})` : '')
                : props.placeholder || t('components.new-desktop.os-template-select.placeholder')
            }}
          </span>
          <ChevronDown class="w-4 h-4 text-gray-warm-500 ml-auto shrink-0" />
        </button>
      </ComboboxTrigger>
    </ComboboxAnchor>
    <ComboboxList align="start" class="p-0 w-(--reka-popper-anchor-width)">
      <div class="flex items-center px-3.5 py-2.5 border-b border-gray-200">
        <Search class="mr-2 h-5 w-5 shrink-0 opacity-50" />
        <ComboboxInput
          v-model="search"
          auto-focus
          :placeholder="t('components.new-desktop.os-template-select.search-placeholder')"
          class="p-0 border-0 shadow-none h-auto text-md text-gray-warm-900 font-medium placeholder:text-gray-warm-500 focus-visible:ring-0"
        />
      </div>
      <div class="max-h-65 overflow-y-auto p-1">
        <p v-if="matchingOptions.length === 0" class="px-2.5 py-2.5 text-sm text-gray-warm-500">
          {{ t('components.new-desktop.os-template-select.not-found') }}
        </p>
        <template v-else>
          <ComboboxItem
            v-for="option in visibleOptions"
            :key="option.id"
            :value="option.id"
            class="justify-start gap-1 p-2.5 text-md text-gray-warm-900 font-medium data-highlighted:bg-brand-100 data-highlighted:cursor-pointer"
          >
            <span class="truncate">{{ option.name }}</span>
            <span v-if="option.vers" class="text-gray-warm-500">({{ option.vers }})</span>
            <Check
              :class="
                cn(
                  'ml-auto h-4 w-4 shrink-0',
                  props.modelValue === option.id ? 'opacity-100' : 'opacity-0'
                )
              "
            />
          </ComboboxItem>
          <p v-if="hiddenResultsCount > 0" class="px-2.5 py-2.5 text-sm text-gray-warm-500">
            {{
              t('components.new-desktop.os-template-select.more-results', {
                count: hiddenResultsCount
              })
            }}
          </p>
        </template>
      </div>
    </ComboboxList>
  </Combobox>
</template>
