<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { z } from 'zod'

import { useForm, type AnyFieldApi } from '@tanstack/vue-form'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { forgotPasswordMutation } from '@/gen/oas/authentication/@tanstack/vue-query.gen'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const categoryId = computed(() => {
  const id = route.query.categoryId
  return typeof id === 'string' ? id : ''
})

type AlertType = 'sent' | 'error'
const alertType = ref<AlertType | null>(null)
const countdown = ref<number>(0)
let countdownInterval: ReturnType<typeof setInterval> | null = null

const { mutateAsync: sendForgotPassword, isPending: isSending } =
  useMutation(forgotPasswordMutation())

const form = useForm({
  defaultValues: { email: '' },
  validators: {
    onChange: ({ value }) => {
      if (!z.email().safeParse(value.email).success) {
        return { fields: { email: t('views.forgot-password.invalid-email') } }
      }
    },
    onSubmit: ({ value }) => {
      if (!z.email().safeParse(value.email).success) {
        return { fields: { email: t('views.forgot-password.invalid-email') } }
      }
    }
  },
  async onSubmit({ value }) {
    if (!value.email || isSending.value) return
    alertType.value = null
    try {
      await sendForgotPassword({ body: { category_id: categoryId.value, email: value.email } })
      startCountdown()
    } catch {
      alertType.value = 'error'
    }
  }
})

onMounted(() => {
  if (!categoryId.value) {
    router.push({ name: 'login' })
  }
})

watch(locale, () => form.validate('change'))

onBeforeUnmount(() => {
  if (countdownInterval) clearInterval(countdownInterval)
})

const startCountdown = () => {
  alertType.value = 'sent'
  countdown.value = 10
  if (countdownInterval) clearInterval(countdownInterval)
  countdownInterval = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      if (countdownInterval) clearInterval(countdownInterval)
      router.push({ name: 'login' })
    }
  }, 1000)
}

const showForm = computed(() => alertType.value !== 'sent')

const emailValue = form.useStore((state) => state.values.email)
const submissionAttempts = form.useStore((state) => state.submissionAttempts)

watch(emailValue, () => {
  if (alertType.value === 'error') alertType.value = null
})

const isInvalid = (field: AnyFieldApi) => submissionAttempts.value > 0 && !field.state.meta.isValid

const layoutTitle = computed(() =>
  alertType.value === 'sent'
    ? t('views.forgot-password.title-sent')
    : t('views.forgot-password.title')
)
const layoutDescription = computed(() =>
  alertType.value === 'sent' ? '' : t('views.forgot-password.description')
)
</script>

<template>
  <LoginLayout v-if="categoryId" :title="layoutTitle" :description="layoutDescription">
    <template #default>
      <div class="flex flex-col space-y-4">
        <Alert v-if="alertType === 'error'" variant="destructive">
          <AlertDescription>
            {{ t('views.forgot-password.error-generic') }}
          </AlertDescription>
        </Alert>

        <Alert v-if="alertType === 'sent'" class="border-success-100 bg-success-50">
          <AlertDescription class="text-success-800">
            {{ t('views.forgot-password.email-sent') }}
            <span class="block mt-2 text-xs">
              {{ t('views.forgot-password.redirecting', { seconds: countdown }) }}
            </span>
          </AlertDescription>
        </Alert>

        <form
          v-if="showForm"
          class="flex flex-col gap-4"
          @submit.prevent="form.handleSubmit"
          novalidate
        >
          <FieldGroup>
            <form.Field v-slot="{ field }" name="email">
              <Field :data-invalid="isInvalid(field)">
                <FieldLabel :for="field.name">
                  {{ t('views.forgot-password.email-label') }}
                </FieldLabel>
                <InputField
                  :id="field.name"
                  :name="field.name"
                  icon="mail-01"
                  :model-value="field.state.value"
                  :destructive="isInvalid(field)"
                  :placeholder="t('views.forgot-password.email-placeholder')"
                  autocomplete="off"
                  type="email"
                  @blur="field.handleBlur"
                  @input="field.handleChange(($event.target as HTMLInputElement).value)"
                />
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </Field>
            </form.Field>
          </FieldGroup>

          <div class="flex flex-col gap-4 mt-4">
            <Button hierarchy="primary" size="lg" type="submit" :disabled="isSending">
              {{ t('views.forgot-password.buttons.reset') }}
            </Button>
            <Button
              hierarchy="secondary-gray"
              size="lg"
              type="button"
              @click="router.push({ name: 'login' })"
            >
              {{ t('views.forgot-password.go-login') }}
            </Button>
          </div>
        </form>

        <Button
          v-if="alertType === 'sent'"
          hierarchy="secondary-gray"
          size="lg"
          type="button"
          @click="router.push({ name: 'login' })"
        >
          {{ t('views.forgot-password.go-login') }}
        </Button>
      </div>
    </template>
  </LoginLayout>
</template>
