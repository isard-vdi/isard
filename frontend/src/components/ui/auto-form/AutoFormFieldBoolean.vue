<script setup lang="ts">
import { computed } from 'vue'
import { beautifyObjectName } from './utils'
import type { FieldProps } from './interface'
import AutoFormLabel from './AutoFormLabel.vue'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormMessage
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'

const props = defineProps<FieldProps>()

const booleanComponent = computed(() => (props.config?.component === 'switch' ? Switch : Checkbox))
</script>

<template>
  <FormField v-slot="slotProps" :name="fieldName">
    <FormItem>
      <div class="space-y-0 mb-3 flex items-center gap-3">
        <FormControl>
          <slot v-bind="slotProps">
            <component
              :is="booleanComponent"
              v-bind="{ ...slotProps.componentField }"
              :disabled="disabled"
              :checked="slotProps.componentField.modelValue"
              @update:checked="slotProps.componentField['onUpdate:modelValue']"
            />
          </slot>
        </FormControl>
        <!-- TODO: size prop -->
        <!-- https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=1097-63652&m=dev -->
        <AutoFormLabel
          v-if="!config?.hideLabel"
          :required="required"
          class="text-gray-warm-700 text-[16px]"
        >
          {{ config?.label || beautifyObjectName(label ?? fieldName) }}
        </AutoFormLabel>
      </div>

      <FormDescription v-if="config?.description">
        {{ config.description }}
      </FormDescription>
      <FormMessage />
    </FormItem>
  </FormField>
</template>
