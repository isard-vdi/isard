<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { z } from 'zod'

import { useForm, type AnyFieldApi } from '@tanstack/vue-form'
import { removeToken as removeAuthToken, useCookies as useAuthCookies } from '@/lib/auth'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { setUserEmailMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const { t } = useI18n()
const cookies = useAuthCookies()

const apiError = ref<string>('')
const successMessage = ref<string>('')

const formSchema = z.object({
  email: z.string().email({ message: t('views.verify-email.invalid-email') })
})

const form = useForm({
  defaultValues: { email: '' },
  validators: {
    onChange: formSchema
  },
  async onSubmit({ value }) {
    if (!value.email || isSubmitting.value) return

    apiError.value = ''
    successMessage.value = ''

    try {
      await setUserEmailMutation({ body: { email: value.email } })
      successMessage.value = t('views.verify-email.success')
    } catch (error: unknown) {
      const descriptionCode =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { description_code?: string } } }).response?.data
              ?.description_code
          : undefined

      if (descriptionCode) {
        const errorKey = `components.profile.email-verification-modal.errors.${descriptionCode}`
        apiError.value = t(errorKey)
      } else {
        apiError.value = t('views.verify-email.error-generic')
      }
    }
  }
})

const { mutateAsync: setUserEmailMutation, isPending: isSubmitting } = useMutation(
  setUserEmailMutation()
)

const isValid = form.useStore((state) => state.isValid)
const emailValue = form.useStore((state) => state.values.email)
const isFormValid = computed(() => !!emailValue.value && isValid.value)

const isInvalid = (field: AnyFieldApi) => field.state.meta.isTouched && !field.state.meta.isValid

const handleLogout = () => {
  removeAuthToken(cookies)
  window.location.pathname = '/login'
}
</script>

<template>
  <LoginLayout
    :title="t('views.verify-email.title')"
    :description="t('views.verify-email.description')"
  >
    <template #default>
      <div class="flex flex-col space-y-4">
        <Alert v-if="apiError" variant="destructive">
          <AlertDescription>{{ apiError }}</AlertDescription>
        </Alert>

        <Alert v-if="successMessage" class="border-success-100 bg-success-50">
          <AlertDescription class="text-success-800">{{ successMessage }}</AlertDescription>
        </Alert>

        <form class="flex flex-col gap-4" @submit.prevent="form.handleSubmit">
          <FieldGroup>
            <form.Field v-slot="{ field }" name="email">
              <Field :data-invalid="isInvalid(field)">
                <FieldLabel :for="field.name">
                  {{ t('views.verify-email.email-label') }}
                </FieldLabel>
                <InputField
                  :id="field.name"
                  :name="field.name"
                  icon="mail-01"
                  :model-value="field.state.value"
                  :destructive="isInvalid(field)"
                  :placeholder="t('views.verify-email.email-placeholder')"
                  autocomplete="off"
                  type="email"
                  @blur="field.handleBlur"
                  @input="field.handleChange(($event.target as HTMLInputElement).value)"
                />
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </Field>
            </form.Field>
          </FieldGroup>

          <div class="flex flex-col gap-2">
            <Button
              hierarchy="primary"
              size="md"
              :disabled="!isFormValid || isSubmitting"
              type="submit"
            >
              {{ t('views.verify-email.buttons.verify') }}
            </Button>
            <Button hierarchy="secondary-gray" size="md" type="button" @click="handleLogout">
              {{ t('views.verify-email.buttons.logout') }}
            </Button>
          </div>
        </form>
      </div>
    </template>
  </LoginLayout>
</template>
