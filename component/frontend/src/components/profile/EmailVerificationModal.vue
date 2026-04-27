<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import Modal from '@/components/modal/Modal.vue'
import { z } from 'zod'
import { Button } from '@/components/ui/button'

import { useForm, type AnyFieldApi } from '@tanstack/vue-form'
import { InputField } from '@/components/input-field'
import { Icon } from '@/components/icon'
import { useI18n } from 'vue-i18n'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { setUserEmailMutation, getUserOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  open?: boolean
  currentEmail?: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  currentEmail: ''
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const apiError = ref<string>('')

const defaultValues = {
  email: ''
}

const formSchema = z.object({
  email: z
    .string()
    .email({ message: t('components.profile.email-verification-modal.invalid-email') })
})

const form = useForm({
  defaultValues,
  validators: {
    onChange: formSchema
  },
  async onSubmit({ value }) {
    if (!value.email || isRequestingVerification.value) return

    apiError.value = ''

    try {
      await setUserEmail({ body: { email: form.getFieldValue('email') } })
      await queryClient.invalidateQueries({ queryKey: getUserOptions() })
      handleClose()
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
        apiError.value = t('components.profile.email-verification-modal.error-generic')
      }
    }
  }
})

watch(
  () => props.open,
  (newVal) => {
    if (newVal) {
      form.reset()
      form.setFieldValue('email', props.currentEmail || '')
      apiError.value = ''
      return
    }

    form.reset()
    apiError.value = ''
  }
)

const handleClose = () => {
  emit('update:open', false)
  form.reset()
  apiError.value = ''
}

const { mutateAsync: setUserEmail, isPending: isRequestingVerification } =
  useMutation(setUserEmailMutation())

const isValid = form.useStore((state) => state.isValid)
const emailValue = form.useStore((state) => state.values.email)
const isFormValid = computed(() => !!emailValue.value && isValid.value)

const isInvalid = (field: AnyFieldApi) => field.state.meta.isTouched && !field.state.meta.isValid
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.profile.email-verification-modal.title')"
    size="md"
    :close-on-backdrop-click="true"
    @close="handleClose"
  >
    <form class="flex flex-col px-2 pb-2 gap-4" @submit.prevent="form.handleSubmit">
      <!-- API Error Alert -->
      <div v-if="apiError" class="rounded-md bg-error-50 border border-error-200 p-3">
        <p class="text-sm font-medium text-error-700">{{ apiError }}</p>
      </div>

      <!-- Description -->
      <p class="text-sm text-gray-warm-700">
        {{ t('components.profile.email-verification-modal.description') }}
      </p>

      <!-- Email input -->
      <FieldGroup>
        <form.Field v-slot="{ field }" name="email">
          <Field :data-invalid="isInvalid(field)">
            <FieldLabel :for="field.name">
              {{ t('components.profile.email-verification-modal.email-label') }}
            </FieldLabel>
            <InputField
              :id="field.name"
              :name="field.name"
              icon="mail-01"
              :model-value="field.state.value"
              :destructive="isInvalid(field)"
              :placeholder="t('components.profile.email-verification-modal.email-placeholder')"
              autocomplete="off"
              type="email"
              @blur="field.handleBlur"
              @input="field.handleChange(($event.target as HTMLInputElement).value)"
            />
            <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
          </Field>
        </form.Field>
      </FieldGroup>
    </form>

    <template #footer>
      <div class="w-full flex justify-center gap-3 px-6">
        <Button
          hierarchy="secondary-gray"
          size="md"
          :disabled="isRequestingVerification"
          @click="handleClose"
        >
          {{ t('components.profile.email-verification-modal.buttons.cancel') }}
        </Button>
        <Button
          hierarchy="primary"
          size="md"
          :disabled="!isFormValid || isRequestingVerification"
          @click="form.handleSubmit"
        >
          {{ t('components.profile.email-verification-modal.buttons.verify') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
