<script setup lang="ts">
import type { HTMLAttributes, InputHTMLAttributes } from 'vue'
import { InputGroup, InputGroupInput, InputGroupAddon } from '../ui/input-group'
import { Icon } from '@/components/icon'

const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    placeholder?: string
    icon?: string
    destructive?: boolean
    disabled?: boolean
    readonly?: boolean
    type?: InputHTMLAttributes['type']
    class?: HTMLAttributes['class']
    id?: string
    name?: string
    required?: boolean
  }>(),
  {
    modelValue: undefined,
    placeholder: undefined,
    icon: undefined,
    type: 'text',
    destructive: false,
    disabled: false,
    readonly: false,
    class: undefined,
    name: undefined
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  blur: [event: FocusEvent]
  input: [event: Event]
}>()
</script>

<template>
  <InputGroup :destructive="destructive" :disabled="disabled" :class="props.class">
    <InputGroupAddon v-if="icon">
      <div>
        <Icon :name="icon" size="md" stroke-color="gray-warm-500" />
      </div>
    </InputGroupAddon>
    <InputGroupInput
      v-bind="$attrs"
      :id="id"
      :name="name"
      :type="type"
      :model-value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :readonly="readonly"
      @update:model-value="emit('update:modelValue', $event)"
      @blur="emit('blur', $event)"
      @input="emit('input', $event)"
    />

    <InputGroupAddon v-if="props.destructive" align="inline-end">
      <Icon name="alert-circle" size="xs" stroke-color="error-500" />
    </InputGroupAddon>
  </InputGroup>
</template>
