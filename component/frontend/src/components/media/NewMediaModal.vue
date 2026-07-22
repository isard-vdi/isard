<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import * as z from 'zod'

import { Modal } from '@/components/modal'
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'

import { createMediaMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ErrorResponse } from '@/gen/oas/apiv4'

import dotGrid from '@/assets/img/modal/dot-grid.svg?component'
import newMediaImg from '@/assets/img/modal/new-media.svg'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const mediaKinds = [
  { value: 'iso', label: t('components.media.new.fields.kind.options.iso') },
  { value: 'floppy', label: t('components.media.new.fields.kind.options.floppy') }
]

const formSchema = z.object({
  name: z
    .string()
    .trim()
    .min(4, t('components.media.new.validation.min-length', { min: 4 }))
    .max(50, t('components.media.new.validation.max-length', { max: 50 })),
  url: z
    .httpUrl(t('components.media.new.validation.invalid-url'))
    .trim()
    .min(1, t('forms.validation.required'))
    .refine((val) => val.startsWith('https://'), {
      message: t('components.media.new.validation.https-required')
    }),
  description: z
    .string()
    .trim()
    .max(255, t('components.media.new.validation.max-length', { max: 255 })),
  kind: z.string().min(1, t('forms.validation.required'))
})

const creationError = ref<string | null>(null)

const { mutate: createMedia, isPending: createMediaIsPending } = useMutation({
  ...createMediaMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['getUserMedia'] })
    form.reset()
    creationError.value = null
    emit('close')
  },
  onError: (error) => {
    const errorResponse = error as ErrorResponse
    creationError.value = errorResponse.description_code || 'generic'

    if (errorResponse.description_code === 'duplicated_name') {
      form.getFieldInfo('name').instance?.setErrorMap({
        onSubmit: t('components.media.new.errors.duplicated_name')
      })
    }
  }
})

const form = useForm({
  defaultValues: reactive({
    name: '',
    url: '',
    description: '',
    kind: 'iso'
  }),
  validators: {
    onChange: formSchema
  },
  onSubmit: ({ value }) => {
    creationError.value = null
    createMedia({
      body: {
        name: value.name,
        url: value.url,
        description: value.description,
        kind: value.kind as any,
        allowed: {
          users: false,
          groups: false
        },
        hypervisors_pools: ['default']
      }
    })
  }
})

const isFormDirty = form.useStore(
  (state) => !!(state.values.name || state.values.url || state.values.description)
)

function setMediaNameFromUrl() {
  const name = form.getFieldValue('name')
  if (!name) {
    const url = form.getFieldValue('url')
    const lastSegment = url.split('/').pop() || ''
    if (lastSegment) {
      form.setFieldValue('name', lastSegment)
    }
  }
}

function isInvalid(field: any) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

const handleClose = () => {
  if (createMediaIsPending.value) return
  form.reset()
  creationError.value = null
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    :close-on-backdrop-click="!isFormDirty"
    :title="t('components.media.new.title')"
    class="max-w-120"
    @close="handleClose"
  >
    <div
      class="relative w-full overflow-hidden flex flex-col items-center justify-center pointer-events-none select-none shrink min-h-0 [@media(max-height:500px)]:hidden"
    >
      <component
        :is="dotGrid"
        class="absolute h-full opacity-30 max-w-94 mt-1"
        :style="{
          fill: 'var(--gray-warm-300)',
          maskImage: 'linear-gradient(to bottom, black 10%, transparent 100%)'
        }"
        aria-hidden="true"
      />
      <img :src="newMediaImg" class="max-h-[min(224px,30vh)] relative z-20 w-full mt-5" />
    </div>

    <Alert v-if="creationError" variant="destructive" class="my-2">
      <AlertTitle>{{ t(`api.new-media.errors.${creationError}.title`) }}</AlertTitle>
      <AlertDescription>{{
        t(`api.new-media.errors.${creationError}.description`)
      }}</AlertDescription>
    </Alert>

    <form
      id="new-media-form"
      class="flex shrink-0 flex-col gap-4"
      @submit.prevent="form.handleSubmit"
    >
      <!-- URL -->
      <form.Field v-slot="{ field }" name="url">
        <Field orientation="vertical">
          <FieldLabel :for="field.name">
            {{ t('components.media.new.fields.url.label') }}
          </FieldLabel>
          <FieldContent>
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :placeholder="t('components.media.new.fields.url.placeholder')"
              :destructive="isInvalid(field)"
              autocomplete="off"
              type="text"
              class="w-full"
              @blur="
                () => {
                  field.handleBlur()
                  setMediaNameFromUrl()
                }
              "
              @input="field.handleChange($event.target.value)"
            />
          </FieldContent>
          <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
        </Field>
      </form.Field>

      <!-- Name -->
      <form.Field v-slot="{ field }" name="name">
        <Field orientation="vertical">
          <FieldLabel :for="field.name">
            {{ t('components.media.new.fields.name.label') }}
          </FieldLabel>
          <FieldContent>
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :placeholder="t('components.media.new.fields.name.placeholder')"
              :destructive="isInvalid(field)"
              autocomplete="off"
              type="text"
              maxlength="50"
              class="w-full"
              @blur="field.handleBlur"
              @input="field.handleChange($event.target.value)"
            />
          </FieldContent>
          <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
        </Field>
      </form.Field>

      <!-- TODO: Add drag and drop / file upload input for media files -->

      <!-- Description -->
      <form.Field v-slot="{ field }" name="description">
        <Field orientation="vertical">
          <FieldLabel :for="field.name">
            {{ t('components.media.new.fields.description.label') }}
          </FieldLabel>
          <FieldContent>
            <Textarea
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :placeholder="t('components.media.new.fields.description.placeholder')"
              :destructive="isInvalid(field)"
              maxlength="255"
              class="w-full bg-base-white"
              @blur="field.handleBlur"
              @input="field.handleChange($event.target.value)"
            />
          </FieldContent>
          <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
        </Field>
      </form.Field>

      <!-- Kind -->
      <form.Field v-slot="{ field }" name="kind">
        <Field orientation="vertical">
          <FieldLabel :for="field.name">
            {{ t('components.media.new.fields.kind.label') }}
          </FieldLabel>
          <FieldContent>
            <Select
              :name="field.name"
              :model-value="field.state.value"
              @update:model-value="field.handleChange"
            >
              <SelectTrigger :aria-invalid="isInvalid(field)" class="w-full">
                <SelectValue :placeholder="t('components.media.new.fields.kind.placeholder')" />
              </SelectTrigger>
              <SelectContent position="item-aligned">
                <SelectItem v-for="kind in mediaKinds" :key="kind.value" :value="kind.value">
                  {{ kind.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </FieldContent>
          <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
        </Field>
      </form.Field>
    </form>

    <template #footer>
      <div class="flex w-full justify-center gap-3 px-6 pb-6">
        <Button hierarchy="link-gray" :disabled="createMediaIsPending" @click="handleClose">
          {{ t('forms.common.cancel') }}
        </Button>
        <form.Subscribe v-slot="{ canSubmit }">
          <Button
            type="submit"
            form="new-media-form"
            :disabled="!canSubmit || createMediaIsPending"
          >
            {{ t('components.media.new.submit') }}
          </Button>
        </form.Subscribe>
      </div>
    </template>
  </Modal>
</template>
