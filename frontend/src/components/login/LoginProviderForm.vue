<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { AutoForm } from '@/components/ui/auto-form'
import { Button } from '@/components/ui/button'
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'

const { t } = useI18n()

const schema = z.object({
  username: z.string(),
  password: z.string()
})

const fieldConfig = computed(() => {
  return {
    username: {
      label: t('components.login.login-provider-form.username'),
    },
    password: {
      label: t('components.login.login-provider-form.password'),
      inputProps: {
        type: 'password'
      }
    }
  }
})

const form = useForm({
  validationSchema: toTypedSchema(schema)
})

const onSubmit = form.handleSubmit((values) => {
  emit('submit', values)
  console.log('Form submitted!', values)
})

const emit = defineEmits<{
  submit: [data: typeof schema._output]
}>()
</script>
<template>
  <AutoForm
    :form="form"
    :schema="schema"
    :field-config="fieldConfig"
    class="space-y-5"
    @submit="onSubmit"
  >
    <a
      href="/forgot-password"
      class="block m-y-1 font-semibold text-center text-brand-500 hover:underline"
      >{{ t('components.login.login-provider-form.forgot-password') }}</a
    >

    <Button type="submit" size="lg" class="w-full">{{ t('components.login.login-provider-form.login') }}</Button>
  </AutoForm>
</template>
