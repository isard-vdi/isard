<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'
import { provideFormSchema } from '@/composables/useFormSchema'
import * as z from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { InputField } from '@/components/input-field'
import { Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { vAutofocus } from '@/directives/autofocus'

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

const showCode = ref(false)

const toggleCodeLabel = computed(() =>
  showCode.value
    ? t('components.register.register-form.hide-code')
    : t('components.register.register-form.show-code')
)

const toggleShowCode = () => {
  showCode.value = !showCode.value
}

const onCancel = () => {
  emit('cancel')
}

const formSchema = z.object({
  code: z.string().nonempty({ error: t('forms.validation.required') })
})

provideFormSchema(formSchema)
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
          v-autofocus
          :name="field.name"
          :model-value="field.state.value"
          :aria-invalid="isInvalid(field)"
          :destructive="isInvalid(field)"
          autocomplete="off"
          :type="showCode ? 'text' : 'password'"
          @blur="field.handleBlur"
          @input="field.handleChange($event.target.value)"
        >
          <template #inline-end>
            <div class="flex items-center gap-2 pr-1">
              <Separator orientation="vertical" class="h-5" />
              <Tooltip>
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="cursor-pointer rounded-md focus:ring-3 focus:ring-gray"
                    :aria-label="toggleCodeLabel"
                    :aria-pressed="showCode"
                    @click="toggleShowCode"
                  >
                    <Icon
                      :name="showCode ? 'eye-off' : 'eye'"
                      size="md"
                      stroke-color="gray-warm-500"
                    />
                  </button>
                </TooltipTrigger>
                <TooltipContent :title="toggleCodeLabel" />
              </Tooltip>
            </div>
          </template>
        </InputField>
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
