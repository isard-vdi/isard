<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { InputField } from '@/components/input-field'

const { t } = useI18n()

interface Props {
  text?: string
  hideForgotPassword?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  text: undefined,
  hideForgotPassword: false
})

const emit = defineEmits<{
  submit: [data: z.output<typeof formSchema>]
  forgotPassword: []
}>()

const onForgotPassword = () => {
  emit('forgotPassword')
}

const formSchema = z.object({
  username: z.string().nonempty({ error: t('forms.validation.required') }),
  password: z.string().nonempty({ error: t('forms.validation.required') })
})

const form = useForm({
  defaultValues: {
    username: '',
    password: ''
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
    <form.Field v-slot="{ field }" name="username">
      <Field :data-invalid="isInvalid(field)">
        <FieldLabel :for="field.name">{{
          t('components.login.login-provider-form.username')
        }}</FieldLabel>
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
    <form.Field v-slot="{ field }" name="password">
      <Field :data-invalid="isInvalid(field)">
        <FieldLabel :for="field.name">{{
          t('components.login.login-provider-form.password')
        }}</FieldLabel>
        <InputField
          :id="field.name"
          :name="field.name"
          :model-value="field.state.value"
          :aria-invalid="isInvalid(field)"
          :destructive="isInvalid(field)"
          autocomplete="off"
          type="password"
          @blur="field.handleBlur"
          @input="field.handleChange($event.target.value)"
        />
        <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
      </Field>
    </form.Field>

    <Button
      v-if="!props.hideForgotPassword"
      type="button"
      hierarchy="link-color"
      class="p-0 text-brand-600"
      @click="onForgotPassword"
      >{{ t('components.login.login-provider-form.forgot-password') }}</Button
    >

    <Button type="submit" size="lg" class="w-full">{{
      props.text || t('components.login.login-provider-form.login')
    }}</Button>
  </form>
</template>
