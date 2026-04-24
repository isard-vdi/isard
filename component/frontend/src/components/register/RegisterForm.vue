<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { InputField } from '@/components/input-field'

const { t } = useI18n()

interface Props {
  submitText?: string
  cancelText?: string
}

const props = withDefaults(defineProps<Props>(), {
  submitText: undefined,
  cancelText: undefined
})

const emit = defineEmits<{
  submit: [data: z.output<typeof formSchema>]
  cancel: []
}>()

const onCancel = () => {
  emit('cancel')
}

const formSchema = z.object({
  code: z.string().nonempty({ error: t('forms.validation.required') })
})

const form = useForm({
  defaultValues: {
    code: ''
  },
  validators: {
    onSubmit: formSchema
  },
  onSubmit: async ({ value }) => {
    emit('submit', value)
  }
})

function isInvalid(field) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}
</script>

<template>
  <form class="flex flex-col gap-5" @submit.prevent="form.handleSubmit">
    <form.Field v-slot="{ field }" name="code">
      <Field :data-invalid="isInvalid(field)">
        <FieldLabel :for="field.name">{{ t('components.register.register-form.code') }}</FieldLabel>
        <InputField
          :id="field.name"
          :name="field.name"
          :model-value="field.state.value"
          :aria-invalid="isInvalid(field)"
          :destructive="isInvalid(field)"
          autocomplete="off"
          type="text"
          @blur="field.handleBlur"
          @input="field.handleChange($event.target.value)"
        />
        <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
      </Field>
    </form.Field>

    <Button type="submit" size="lg" class="w-full">{{
      props.submitText || t('components.register.register-form.register')
    }}</Button>
    <Button type="button" size="lg" class="w-full" hierarchy="destructive" @click="onCancel">{{
      props.cancelText || t('components.register.register-form.cancel')
    }}</Button>
  </form>
</template>
