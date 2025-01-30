<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { AutoForm } from '@/components/ui/auto-form'
import { Button } from '@/components/ui/button'
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'

const { t } = useI18n()

interface Props {
  submitText?: string
  cancelText?: string
}

const schema = z.object({
  code: z.string()
})

const fieldConfig = computed(() => {
  return {
    code: {
      label: t('components.register.register-form.code'),
      inputProps: {
        autoComplete: 'off'
      }
    }
  }
})

const form = useForm({
  validationSchema: toTypedSchema(schema)
})

const onSubmit = form.handleSubmit((values) => {
  emit('submit', values)
})

const props = withDefaults(defineProps<Props>(), {
  submitText: undefined,
  cancelText: undefined
})
const emit = defineEmits<{
  submit: [data: typeof schema._output]
  cancel: []
}>()

const onCancel = () => {
  emit('cancel')
}
</script>
<template>
  <AutoForm
    :form="form"
    :schema="schema"
    :field-config="fieldConfig"
    class="flex flex-col space-y-5"
    @submit="onSubmit"
  >
    <Button type="submit" size="lg" class="w-full">{{
      props.submitText || t('components.register.register-form.register')
    }}</Button>
    <Button type="button" size="lg" class="w-full" hierarchy="destructive" @click="onCancel">{{
      props.cancelText || t('components.register.register-form.cancel')
    }}</Button>
  </AutoForm>
</template>
