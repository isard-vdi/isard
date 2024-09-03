<script setup lang="ts">
import { computed, ref } from 'vue'
import { useVModel } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { Check, ChevronDown } from 'lucide-vue-next'
import { type GetCategoriesResponse } from '@/gen/oas/api'
import { cn } from '@/lib/utils'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandInput,
  CommandEmpty,
  CommandList,
  CommandGroup,
  CommandItem
} from '@/components/ui/command'

const { t } = useI18n()

interface Props {
  categories: GetCategoriesResponse
  modelValue?: GetCategoriesResponse[number]
}

const props = defineProps<Props>()
const emits = defineEmits<{
  (e: 'update:modelValue', payload: (typeof props.categories)[number]): void
}>()

const categoriesToShow = computed(() => props.categories.filter((category) => category.frontend))

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true
})

const open = ref(false)
const focused = ref(false)
const focus = () => {
  focused.value = true
  open.value = true
}

const filterFunction = (list: GetCategoriesResponse, searchTerm: string) => {
  return list.filter((category) => {
    return category.name.toLowerCase().includes(searchTerm.toLowerCase())
  })
}

defineExpose({
  focus
})
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        role="combobox"
        :aria-expanded="open"
        hierarchy="secondary-gray"
        :class="
          cn(
            'justify-start font-medium',
            modelValue ? 'text-gray-warm-900' : 'text-gray-warm-500',
            focused && modelValue === undefined ? 'ring ring-error' : ''
          )
        "
      >
        {{
          modelValue
            ? categoriesToShow.find((cat) => modelValue && cat.id == modelValue.id)?.name
            : t('components.login.login-categories-dropdown.placeholder')
        }}
        <ChevronDown class="w-4 h-4 text-gray-warm-500 ml-auto" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="border-0 p-0 w-[360px]">
      <Command v-model:modelValue="modelValue" :filter-function="filterFunction">
        <CommandInput :placeholder="t('components.login.login-categories-dropdown.placeholder')" />
        <CommandEmpty>{{ t('components.login.login-categories-dropdown.not-found') }}</CommandEmpty>
        <CommandList>
          <CommandGroup>
            <CommandItem
              v-for="cat in categoriesToShow"
              :key="cat.id"
              :value="cat"
              @select="open = false"
            >
              {{ cat.name }}
              <Check
                :class="
                  cn(
                    'ml-auto h-4 w-4',
                    modelValue && modelValue.id === cat.id ? 'opacity-100' : 'opacity-0'
                  )
                "
              />
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </PopoverContent>
  </Popover>
</template>
