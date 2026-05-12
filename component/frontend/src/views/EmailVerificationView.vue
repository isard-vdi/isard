<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { jwtDecode } from 'jwt-decode'
import { z } from 'zod'

import { useForm, type AnyFieldApi } from '@tanstack/vue-form'
import {
  removeToken as removeAuthToken,
  TokenType,
  useCookies as useAuthCookies,
  type TypeClaims
} from '@/lib/auth'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { InputField } from '@/components/input-field'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { setUserEmailMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { verifyEmailMutation } from '@/gen/oas/authentication/@tanstack/vue-query.gen'

type Mode = 'verifying' | 'verified' | 'link-error' | 'form'

const { t } = useI18n()
const route = useRoute()
const cookies = useAuthCookies()

const apiError = ref<string>('')
const successMessage = ref<string>('')

const urlToken = typeof route.query.token === 'string' ? route.query.token : ''

const isEmailVerificationToken = (raw: string): boolean => {
  try {
    const claims = jwtDecode<TypeClaims>(raw)
    return claims?.type === TokenType.EmailVerification
  } catch {
    return false
  }
}

const mode = ref<Mode>(urlToken && isEmailVerificationToken(urlToken) ? 'verifying' : 'form')

const { mutateAsync: verifyEmail } = useMutation(verifyEmailMutation())
const { mutateAsync: setUserEmail, isPending: isSubmitting } = useMutation(setUserEmailMutation())

const goToLogin = () => {
  removeAuthToken(cookies)
  window.location.pathname = '/login'
}

const REDIRECT_SECONDS = 5
const redirectSeconds = ref(REDIRECT_SECONDS)
const isRedirecting = ref(false)
let redirectTimer: ReturnType<typeof setInterval> | null = null

const startRedirectCountdown = () => {
  if (isRedirecting.value) return
  isRedirecting.value = true
  redirectSeconds.value = REDIRECT_SECONDS
  removeAuthToken(cookies)
  redirectTimer = setInterval(() => {
    redirectSeconds.value -= 1
    if (redirectSeconds.value <= 0) {
      if (redirectTimer) clearInterval(redirectTimer)
      redirectTimer = null
      window.location.pathname = '/login'
    }
  }, 1000)
}

onUnmounted(() => {
  if (redirectTimer) clearInterval(redirectTimer)
})

onMounted(async () => {
  if (mode.value !== 'verifying') return
  try {
    await verifyEmail({
      body: {},
      headers: { Authorization: 'Bearer ' + urlToken }
    })
    mode.value = 'verified'
    startRedirectCountdown()
  } catch {
    mode.value = 'link-error'
  }
})

const layoutTitle = computed(() => {
  switch (mode.value) {
    case 'verifying':
      return t('views.verify-email.verifying')
    case 'verified':
      return t('views.verify-email.verified.title')
    case 'link-error':
      return t('views.verify-email.link-error.title')
    default:
      return t('views.verify-email.title')
  }
})

const layoutDescription = computed(() =>
  mode.value === 'form' ? t('views.verify-email.description') : undefined
)

const formSchema = z.object({
  email: z.string().email({ message: t('views.verify-email.invalid-email') })
})

const form = useForm({
  defaultValues: { email: '' },
  validators: {
    onChange: formSchema
  },
  async onSubmit({ value }) {
    if (!value.email || isSubmitting.value || isRedirecting.value) return

    apiError.value = ''
    successMessage.value = ''

    try {
      await setUserEmail({ body: { email: value.email } })
      successMessage.value = t('views.verify-email.success')
      startRedirectCountdown()
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

const isValid = form.useStore((state) => state.isValid)
const emailValue = form.useStore((state) => state.values.email)
const isFormValid = computed(() => !!emailValue.value && isValid.value)

const isInvalid = (field: AnyFieldApi) => field.state.meta.isTouched && !field.state.meta.isValid
</script>

<template>
  <LoginLayout :title="layoutTitle" :description="layoutDescription">
    <template #default>
      <div class="flex flex-col space-y-4">
        <div v-if="mode === 'verifying'" class="flex flex-col items-center gap-3 py-4">
          <Spinner size="md" />
          <p class="text-sm text-gray-600">{{ t('views.verify-email.verifying') }}</p>
        </div>

        <template v-else-if="mode === 'verified'">
          <Alert class="border-success-100 bg-success-50">
            <AlertDescription class="text-success-800">
              {{ t('views.verify-email.verified.description') }}
              <span v-if="isRedirecting" class="block">
                {{ t('views.verify-email.redirecting', { seconds: redirectSeconds }) }}
              </span>
            </AlertDescription>
          </Alert>
          <Button hierarchy="primary" size="md" type="button" @click="goToLogin">
            {{ t('views.verify-email.buttons.login') }}
          </Button>
        </template>

        <template v-else-if="mode === 'link-error'">
          <Alert variant="destructive">
            <AlertDescription>
              {{ t('views.verify-email.link-error.description') }}
            </AlertDescription>
          </Alert>
          <Button hierarchy="primary" size="md" type="button" @click="goToLogin">
            {{ t('views.verify-email.buttons.login') }}
          </Button>
        </template>

        <template v-else>
          <Alert v-if="apiError" variant="destructive">
            <AlertDescription>{{ apiError }}</AlertDescription>
          </Alert>

          <Alert v-if="successMessage" class="border-success-100 bg-success-50">
            <AlertDescription class="text-success-800">
              {{ successMessage }}
              <span v-if="isRedirecting" class="block">
                {{ t('views.verify-email.redirecting', { seconds: redirectSeconds }) }}
              </span>
            </AlertDescription>
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
                :disabled="!isFormValid || isSubmitting || isRedirecting"
                type="submit"
              >
                {{ t('views.verify-email.buttons.verify') }}
              </Button>
              <Button hierarchy="secondary-gray" size="md" type="button" @click="goToLogin">
                {{ t('views.verify-email.buttons.logout') }}
              </Button>
            </div>
          </form>
        </template>
      </div>
    </template>
  </LoginLayout>
</template>
