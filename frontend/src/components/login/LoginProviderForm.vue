<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { AutoForm } from '@/components/ui/auto-form'
import { Button } from '@/components/ui/button'

const schema = z.object({
  username: z.string(),
  password: z.string()
})

const fieldConfig = {
  password: {
    inputProps: {
      type: 'password'
    }
  }
}

const form = useForm({
  validationSchema: toTypedSchema(schema)
})

const onSubmit = form.handleSubmit((values) => {
  console.log('Form submitted!', values)
})
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
      >Has oblidat la contrasenya?</a
    >

    <Button type="submit" size="lg" class="w-full">Iniciar sessió</Button>
  </AutoForm>
</template>
