<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ChevronDown } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList
} from '@/components/ui/command'
import type { AllowedOption } from '.'

interface Props {
  options: AllowedOption[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false
})

const model = defineModel<string | null>({ default: null })

const { t } = useI18n()

const open = ref(false)

const selectedLabel = computed(
  () => props.options.find((option) => option.value === model.value)?.label
)

const pick = (value: string | null) => {
  model.value = value
  open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        role="combobox"
        :aria-expanded="open"
        hierarchy="secondary-gray"
        :disabled="props.disabled"
        :class="
          cn(
            'h-10 w-full justify-start font-medium',
            selectedLabel ? 'text-gray-warm-900' : 'text-gray-warm-500'
          )
        "
        data-slot="group-filter-trigger"
      >
        <span class="truncate">{{
          selectedLabel ?? t('components.allowed-modal.filter.all')
        }}</span>
        <ChevronDown class="ml-auto h-4 w-4 shrink-0 text-gray-warm-500" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" class="w-72 border-0 p-0">
      <Command :model-value="model ?? ''">
        <CommandInput :placeholder="t('components.allowed-modal.search.group.placeholder')" />
        <CommandEmpty>{{ t('components.allowed-modal.search.group.empty') }}</CommandEmpty>
        <CommandList>
          <CommandGroup>
            <CommandItem value="" @select="pick(null)">
              {{ t('components.allowed-modal.filter.all') }}
              <Check :class="cn('ml-auto h-4 w-4 shrink-0', model ? 'opacity-0' : 'opacity-100')" />
            </CommandItem>
            <CommandItem
              v-for="option in props.options"
              :key="option.value"
              :value="option.value"
              @select="pick(option.value)"
            >
              <span class="truncate">{{ option.label }}</span>
              <Check
                :class="
                  cn(
                    'ml-auto h-4 w-4 shrink-0',
                    model === option.value ? 'opacity-100' : 'opacity-0'
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
