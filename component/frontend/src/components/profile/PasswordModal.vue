<script setup lang="ts">
import { watch, onMounted, shallowRef, useId, watchEffect, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { useForm, revalidateLogic, type AnyFieldApi } from '@tanstack/vue-form'

import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import Spinner from '@/components/ui/spinner/Spinner.vue'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'

import {
  getUserPasswordPolicyOptions,
  setUserPasswordMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { PasswordPolicyErrorResponse } from '@/gen/oas/apiv4'

import imgurl from '@/assets/img/password-modal-header.svg'
import { whenever } from '@vueuse/core'

const { t } = useI18n()

const open = defineModel<boolean>('open', { default: false })

const error = shallowRef('')
const errorparams = shallowRef<Record<string, unknown>>({})
const waiting = shallowRef(false)

const id = useId()
function toId(name: string) {
  return `${id}-${name}`
}

const mutation = useMutation({
  ...setUserPasswordMutation(),
  onSuccess() {
    open.value = false
    waiting.value = false
    form.reset()
  },
  onError(err: Error) {
    const resp = JSON.parse(err.message) as PasswordPolicyErrorResponse
    if (resp.description_code === 'wrong_password_entered') {
      form.getFieldInfo('current').instance?.setErrorMap({
        onSubmit: t('components.profile.password-modal.errors.wrong_password_entered')
      })
    } else {
      if (resp.params) errorparams.value = resp.params
      error.value = resp.description_code
    }
    waiting.value = false
  }
})

const { data: policy, isPending: loading } = useQuery({
  ...getUserPasswordPolicyOptions(),
  enabled: open
})

whenever(
  () => !loading.value && open.value,
  () => {
    setTimeout(() => {
      form.setFieldMeta('newPassword', (meta) => ({
        ...meta,
        isTouched: true,
        isDirty: true
      }))

      form.validateField('newPassword', 'change')
    }, 0)
  }
)

const form = useForm({
  defaultValues: {
    current: '',
    newPassword: '',
    newPasswordConfirm: ''
  },
  validationLogic: revalidateLogic({ mode: 'change' }),
  validators: {
    onChange: z
      .object({
        current: z.any(),
        newPassword: z.string(),
        newPasswordConfirm: z.string()
      })
      .refine((data) => data.newPassword === data.newPasswordConfirm, {
        message: t('components.profile.password-modal.errors.mismatch'),
        path: ['newPasswordConfirm']
      })
  },
  onSubmit({ value }) {
    waiting.value = true
    mutation.mutate({
      body: {
        current_password: value.current,
        password: value.newPassword
      }
    })
  }
})

function handleCancel() {
  open.value = false
  form.reset()
}

function isInvalid(field: AnyFieldApi) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

const PASSWORD_REGEX = {
  SPECIAL: /[!@#$%^&*()+\-=[\]{}|;:'",.<>/?]/g,
  DIGITS: /[0-9]/g,
  LOWERCASE: /[a-z]/g,
  UPPERCASE: /[A-Z]/g
} as const

const hasErrors = form.useStore((state) => {
  if (state.isDirty && state.errors.length && state.submissionAttempts) return true
  for (const key of ['current', 'newPassword', 'newPasswordConfirm'] as const) {
    const meta = state.fieldMeta[key]
    if (!!meta && meta.isDirty && meta.errors.length) return true
  }
  return false
})
</script>

<template>
  <Modal
    :title="t('components.profile.password-modal.title')"
    :open="open"
    size="md"
    class="min-h-md"
    @close="handleCancel"
  >
    <img :src="imgurl" alt="" class="pl-2 pr-2" />
    <div v-if="loading">
      <Spinner size="sm" class="my-10 mx-auto" />
    </div>
    <form v-else :id="toId('form')" class="pb-1" @submit.prevent="form.handleSubmit">
      <div
        v-if="error"
        class="block bg-error-25 border border-error-200 text-error-600 px-3 py-2 rounded-md text-sm my-4"
      >
        {{ t('components.profile.password-modal.errors.' + error, errorparams) }}
      </div>
      <div v-if="waiting">
        <Spinner size="sm" class="mx-auto my-4" />
      </div>
      <FieldGroup>
        <form.Field
          name="current"
          :validators="{
            onDynamic: z.string().min(1, t('components.profile.password-modal.errors.required'))
          }"
        >
          <template #default="{ field }">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="toId(field.name)">
                {{ t('components.profile.password-modal.current-password.label') }}
              </FieldLabel>
              <InputField
                :id="toId(field.name)"
                v-model="field.state.value"
                :name="field.name"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                :placeholder="t('components.profile.password-modal.current-password.placeholder')"
                type="password"
                autocomplete="off"
                @blur="field.handleBlur"
                @input="field.handleChange(($event.target as HTMLInputElement).value)"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </template>
        </form.Field>
        <form.Field
          name="newPassword"
          :validators="{
            onChange: z
              .string()
              .min(
                policy!.length,
                t('components.profile.password-modal.errors.password_character_length', {
                  num: policy!.length
                })
              )
              .refine(
                (val) => (val.match(PASSWORD_REGEX.UPPERCASE)?.length ?? 0) >= policy!.uppercase,
                {
                  message: t('components.profile.password-modal.errors.password_uppercase', {
                    num: policy!.uppercase
                  })
                }
              )
              .refine(
                (val) => (val.match(PASSWORD_REGEX.LOWERCASE)?.length ?? 0) >= policy!.lowercase,
                {
                  message: t('components.profile.password-modal.errors.password_lowercase', {
                    num: policy!.lowercase
                  })
                }
              )
              .refine((val) => (val.match(PASSWORD_REGEX.DIGITS)?.length ?? 0) >= policy!.digits, {
                message: t('components.profile.password-modal.errors.password_digits', {
                  num: policy!.digits
                })
              })
              .refine(
                (val) =>
                  (val.match(PASSWORD_REGEX.SPECIAL)?.length ?? 0) >= policy!.special_characters,
                {
                  message: t(
                    'components.profile.password-modal.errors.password_special_characters',
                    {
                      num: policy!.special_characters
                    }
                  )
                }
              )
          }"
        >
          <template #default="{ field }">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="toId(field.name)">
                {{ t('components.profile.password-modal.new-password.label') }}
              </FieldLabel>
              <InputField
                :id="toId(field.name)"
                v-model="field.state.value"
                :name="field.name"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                :placeholder="t('components.profile.password-modal.new-password.placeholder')"
                type="password"
                autocomplete="off"
                @blur="field.handleBlur"
                @input="field.handleChange(($event.target as HTMLInputElement).value)"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </template>
        </form.Field>
        <form.Field
          name="newPasswordConfirm"
          :validators="{
            onDynamic: z.string().min(1, t('components.profile.password-modal.errors.required'))
          }"
        >
          <template #default="{ field }">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="toId(field.name)">
                {{ t('components.profile.password-modal.confirm-new-password.label') }}
              </FieldLabel>
              <InputField
                :id="toId(field.name)"
                v-model="field.state.value"
                :name="field.name"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                :placeholder="
                  t('components.profile.password-modal.confirm-new-password.placeholder')
                "
                type="password"
                autocomplete="off"
                @blur="field.handleBlur"
                @input="field.handleChange(($event.target as HTMLInputElement).value)"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </template>
        </form.Field>
      </FieldGroup>
    </form>
    <template #footer>
      <Button hierarchy="link-color" @click="handleCancel">{{
        t('components.profile.password-modal.buttons.cancel')
      }}</Button>
      <Button
        hierarchy="primary"
        as="button"
        type="submit"
        :form="toId('form')"
        :disabled="loading || waiting || hasErrors"
        >{{ t('components.profile.password-modal.buttons.update') }}</Button
      >
    </template>
  </Modal>
</template>
