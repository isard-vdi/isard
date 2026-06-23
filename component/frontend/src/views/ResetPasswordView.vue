<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { z } from 'zod'
import Spinner from '@/components/ui/spinner/Spinner.vue'
import { useForm, revalidateLogic, type AnyFieldApi } from '@tanstack/vue-form'
import { LoginLayout } from '@/layouts/login'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { resetPasswordMutation } from '@/gen/oas/authentication/@tanstack/vue-query.gen'
import { getUserPasswordPolicyOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import PasswordRequirements from '@/components/password-requirements/PasswordRequirements.vue'
import { cn } from '@/lib/utils'
import { PASSWORD_REGEX } from '@/lib/password'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const { mutateAsync: resetPassword, isPending: isSending } = useMutation({
  ...resetPasswordMutation()
})

const urlToken = computed(() => {
  const tokenId = route.query.token
  return typeof tokenId === 'string' ? tokenId : ''
})

const {
  data: policy,
  isPending: loading,
  error: policyError
} = useQuery({
  ...getUserPasswordPolicyOptions({
    headers: { Authorization: `Bearer ${urlToken.value}` }
  }),
  // The token comes from the reset-password email link and expires after 60 min.
  // A 401 (token_expired) is a permanent, expected outcome here — retrying just
  // delays surfacing policyError by ~7s and re-fires the 401 handler each time.
  retry: false
})

type AlertType = 'sent'
const alertType = ref<AlertType | null>(null)
const countdown = ref<number>(0)
let countdownInterval: ReturnType<typeof setInterval> | null = null

// Error shown in an alert above the form after pressing "Update password":
//  - 'policy'  → the server rejected the password; list the unmet requirement(s)
//  - 'generic' → network/internal error; show a generic "try again" message
type SubmitError = { kind: 'generic' } | { kind: 'policy'; messages: string[] }
const submitError = ref<SubmitError | null>(null)

// description_codes that map to a password-policy requirement. Anything else
// (network failure, internal_server, plain bad_request) is treated as generic.
const POLICY_ERROR_CODES: readonly string[] = [
  'password_character_length',
  'password_uppercase',
  'password_lowercase',
  'password_digits',
  'password_special_characters',
  'password_already_used',
  'password_username'
]

// Shared error body shape across the policy query and the reset mutation.
interface ApiErrorBody {
  error?: string
  msg?: string
  description_code?: string
  params?: { num?: number }
}

// On an HTTP error the generated client throws the parsed JSON body directly
// (e.g. { error, msg, description_code }). Network/abort errors arrive instead
// as a real Error, and a non-JSON body as a raw string — both fall through to
// the generic message.
function parseApiError(err: unknown): ApiErrorBody | null {
  if (err && typeof err === 'object' && !(err instanceof Error)) {
    const body = err as ApiErrorBody
    if (typeof body.description_code === 'string' || typeof body.error === 'string') {
      return body
    }
    return null
  }
  // Fallbacks: a real Error or string body that may carry the JSON inside it.
  const raw = err instanceof Error ? err.message : typeof err === 'string' ? err : null
  if (raw === null) return null
  try {
    return JSON.parse(raw) as ApiErrorBody
  } catch {
    return null
  }
}

// Fatal token problems: the link is unusable, so we replace the form with an
// explanatory alert instead of an inline error.
//  - 'expired' → the reset JWT's exp passed. Detected at page load: the
//                password-policy query carries the same token and 401s with
//                description_code 'token_expired'.
//  - 'invalid' → the link is no longer valid — most often already used to
//                change the password (the policy endpoint returns 200 for an
//                already-used token, so this can only surface at submit time as
//                'invalid_token'), or the token is malformed.
type LinkError = 'expired' | 'invalid'
const submitLinkError = ref<LinkError | null>(null)
const linkError = computed<LinkError | null>(() => {
  if (submitLinkError.value) return submitLinkError.value
  if (!policyError.value) return null
  return parseApiError(policyError.value)?.description_code === 'token_expired'
    ? 'expired'
    : 'invalid'
})

const passwordFormSchema = z
  .object({
    newPassword: z.string().superRefine((val, ctx) => {
      const p = policy.value
      if (!p) return
      const meetsPolicy =
        val.length >= p.length &&
        (val.match(PASSWORD_REGEX.UPPERCASE)?.length ?? 0) >= p.uppercase &&
        (val.match(PASSWORD_REGEX.LOWERCASE)?.length ?? 0) >= p.lowercase &&
        (val.match(PASSWORD_REGEX.DIGITS)?.length ?? 0) >= p.digits &&
        (val.match(PASSWORD_REGEX.SPECIAL)?.length ?? 0) >= p.special_characters
      if (!meetsPolicy) ctx.addIssue({ code: 'custom' })
    }),
    newPasswordConfirm: z.string().min(1, t('components.profile.password-modal.errors.required'))
  })
  .refine((data) => data.newPasswordConfirm === data.newPassword, {
    path: ['newPasswordConfirm'],
    message: t('components.profile.password-modal.errors.mismatch')
  })

const form = useForm({
  defaultValues: {
    newPassword: '',
    newPasswordConfirm: ''
  },
  validationLogic: revalidateLogic({ mode: 'change' }),
  validators: { onDynamic: passwordFormSchema },
  async onSubmit({ value }) {
    if (isSending.value) return
    submitError.value = null
    try {
      await resetPassword({
        body: { password: value.newPassword },
        headers: { Authorization: `Bearer ${urlToken.value}` }
      })
      startCountdown()
    } catch (err) {
      const parsed = parseApiError(err)
      const code = parsed?.description_code
      if (code === 'token_expired') {
        // Token expired between page load and submit — link is dead.
        submitLinkError.value = 'expired'
      } else if (parsed?.error === 'invalid_token' || parsed?.error === 'missing_token') {
        // Already used (or malformed) — the only place the backend reveals this.
        submitLinkError.value = 'invalid'
      } else if (code && POLICY_ERROR_CODES.includes(code)) {
        submitError.value = {
          kind: 'policy',
          messages: [
            t(`components.profile.password-modal.errors.${code}`, { num: parsed?.params?.num ?? 0 })
          ]
        }
      } else {
        submitError.value = { kind: 'generic' }
      }
    }
  }
})

// Live value of the new password field; drives the policy checklist state below.
const newPasswordValue = form.useStore((state) => state.values.newPassword)

// Once the user has pressed "Update password" at least once, the checklist marks
// the still-unmet (client-verifiable) requirements in red. Before that it stays
// neutral so it doesn't nag while the password is being typed.
const submissionAttempts = form.useStore((state) => state.submissionAttempts)

function isInvalid(field: AnyFieldApi) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

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

// When a terminal-state alert (success, or an unusable link) replaces the form,
// move keyboard focus onto it so keyboard and screen-reader users land on the
// new content instead of a control that was just removed. role="alert" still
// announces it; this handles focus placement.
const focusById = (id: string) => nextTick(() => document.getElementById(id)?.focus())
watch(
  () => alertType.value === 'sent',
  (shown) => {
    if (shown) focusById('reset-success-alert')
  }
)
watch(
  () => linkError.value,
  (err) => {
    if (err) focusById('reset-link-error-alert')
  }
)

onBeforeUnmount(() => {
  if (countdownInterval) clearInterval(countdownInterval)
})
</script>

<template>
  <LoginLayout :title="t('views.reset-password.title')">
    <template #default>
      <div class="flex flex-col space-y-4">
        <div v-if="loading">
          <Spinner size="md" class="my-10 mx-auto" />
        </div>
        <template v-else-if="!linkError && alertType !== 'sent'">
          <Alert v-if="submitError" variant="destructive">
            <AlertDescription>
              <template v-if="submitError.kind === 'policy'">
                <p class="font-semibold">
                  {{ t('views.reset-password.submit-error.policy-heading') }}
                </p>
                <ul class="mt-1 flex flex-col gap-1 list-disc pl-5">
                  <li v-for="message in submitError.messages" :key="message">{{ message }}</li>
                </ul>
              </template>
              <template v-else>
                {{ t('views.reset-password.submit-error.generic') }}
              </template>
            </AlertDescription>
          </Alert>
          <div class="relative">
            <div v-if="isSending" class="absolute inset-0 z-10 flex items-center justify-center">
              <Spinner size="md" />
            </div>
            <form
              novalidate
              :class="
                cn(
                  'transition duration-200 space-y-6',
                  isSending && 'pointer-events-none select-none grayscale blur-[3px] opacity-60'
                )
              "
              :aria-busy="isSending"
              @submit.prevent="form.handleSubmit"
            >
              <FieldGroup>
                <form.Field name="newPassword">
                  <template #default="{ field }">
                    <Field>
                      <FieldLabel :for="field.name">
                        {{ t('components.profile.password-modal.new-password.label') }}
                      </FieldLabel>
                      <InputField
                        :id="field.name"
                        v-model="field.state.value"
                        :name="field.name"
                        :placeholder="
                          t('components.profile.password-modal.new-password.placeholder')
                        "
                        type="password"
                        autocomplete="new-password"
                        :aria-invalid="isInvalid(field)"
                        aria-describedby="password-requirements"
                        @blur="field.handleBlur"
                        @input="field.handleChange(($event.target as HTMLInputElement).value)"
                      />
                    </Field>
                  </template>
                </form.Field>
                <form.Field name="newPasswordConfirm">
                  <template #default="{ field }">
                    <Field :data-invalid="isInvalid(field)">
                      <FieldLabel :for="field.name">
                        {{ t('components.profile.password-modal.confirm-new-password.label') }}
                      </FieldLabel>
                      <InputField
                        :id="field.name"
                        v-model="field.state.value"
                        :name="field.name"
                        :aria-invalid="isInvalid(field)"
                        :destructive="isInvalid(field)"
                        :placeholder="
                          t('components.profile.password-modal.confirm-new-password.placeholder')
                        "
                        type="password"
                        autocomplete="new-password"
                        @blur="field.handleBlur"
                        @input="field.handleChange(($event.target as HTMLInputElement).value)"
                      />
                      <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
                    </Field>
                  </template>
                </form.Field>
              </FieldGroup>
              <PasswordRequirements
                v-if="policy"
                :input-password="newPasswordValue"
                :policies="policy"
                :show-errors="submissionAttempts > 0"
              />
              <Button
                class="w-full"
                hierarchy="primary"
                size="lg"
                type="submit"
                :disabled="isSending || loading"
              >
                {{ t('views.reset-password.submit') }}
              </Button>
            </form>
          </div>
        </template>
        <Alert
          v-else-if="alertType === 'sent'"
          id="reset-success-alert"
          tabindex="-1"
          class="border-success-100 bg-success-50"
        >
          <AlertDescription class="text-success-800 font-semibold">
            {{ t('views.reset-password.success.message') }}
            <!-- aria-hidden: the countdown ticks every second; without this the
                 role="alert" region would re-announce the whole message each tick. -->
            <span class="block mt-2 text-xs" aria-hidden="true">
              {{ t('views.reset-password.success.redirecting', { seconds: countdown }) }}
            </span>
          </AlertDescription>
        </Alert>
        <Alert
          v-else-if="linkError"
          id="reset-link-error-alert"
          tabindex="-1"
          variant="destructive"
        >
          <AlertDescription>
            <p class="font-semibold">{{ t(`views.reset-password.${linkError}.title`) }}</p>
            <p class="mt-1">
              {{ t(`views.reset-password.${linkError}.description`) }}
              <strong class="font-semibold">{{
                t(`views.reset-password.${linkError}.action`)
              }}</strong>
            </p>
          </AlertDescription>
        </Alert>
        <Button
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
