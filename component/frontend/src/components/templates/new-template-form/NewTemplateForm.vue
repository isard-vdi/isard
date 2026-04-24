<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'

import {
  getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGetOptions,
  getDesktopInfoApiV4ItemDesktopDesktopIdGetInfoGetOptions,
  createTemplateMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldTitle
} from '@/components/ui/field'
import { InputField } from '@/components/input-field'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import Label from '@/components/ui/label/Label.vue'
import Switch from '@/components/ui/switch/Switch.vue'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Skeleton } from '@/components/ui/skeleton'
import type { ErrorResponse } from '@/gen/oas/apiv4'

const { t, d } = useI18n()

interface Props {
  desktopId: string
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  templateCreated: [templateId: string]
}>()

// ------------------------------------------

const desktopId = ref<string>(props.desktopId)

const { data: desktopInfo, isPending: desktopInfoIsPending } = useQuery(
  getDesktopInfoApiV4ItemDesktopDesktopIdGetInfoGetOptions({
    path: {
      desktop_id: desktopId.value
    }
  })
)
const { data: desktopDetails, isPending: desktopDetailsIsPending } = useQuery(
  getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGetOptions({
    path: {
      desktop_id: desktopId.value
    }
  })
)

const imageUrl = computed(() => {
  return desktopInfo.value?.image?.url || ''
})

const createTemplateErrorCode = ref<string | undefined>(undefined)
const {
  mutate: createTemplateMutation,
  mutateAsync: createTemplateAsync,
  isPending: createTemplateIsPending,
  isError: createTemplateIsError,
  error: createTemplateError,
  data: createTemplateData
} = useMutation({
  ...createTemplateMutation(),
  onSuccess: (data) => {
    emit('templateCreated', data.id)
  },
  onError: (error: Error) => {
    const errorResponse = error as unknown as ErrorResponse
    createTemplateErrorCode.value = errorResponse.description_code

    // Handle name conflict error
    if (errorResponse.description_code === 'new_template_name_exists') {
      form.getFieldInfo('name').instance?.setErrorMap({
        onSubmit: t('views.new-template.form.errors.fields.name.exists')
      })
    }
  }
})

const formSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, t('components.form.validation.required'))
    .min(4, t('components.form.validation.min-length', { min: 4 }))
    .max(50, t('components.form.validation.max-length', { max: 50 })),
  description: z
    .string()
    .trim()
    .max(255, t('components.form.validation.max-length', { max: 255 })),
  enabled: z.boolean()
})

const form = useForm({
  defaultValues: reactive({
    name: computed(() =>
      desktopInfo.value?.name
        ? t(
            'views.new-template.form.sections.preview.fields.name.default',
            { desktop_name: desktopInfo.value.name },
            desktopInfo.value.name
          )
        : ''
    ),
    description: computed(() => desktopInfo.value?.description || ''),
    enabled: true
  }),
  validators: {
    onChange: formSchema
  },
  onSubmit: ({ value }) => {
    createTemplateAsync({
      body: {
        desktop_id: desktopId.value,
        name: value.name,
        description: value.description,
        enabled: value.enabled,
        allowed: {
          users: false,
          groups: false
        }
      }
    })
  }
})

function isInvalid(field) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

const isPending = computed(() => {
  return (
    desktopInfoIsPending.value || desktopDetailsIsPending.value || createTemplateIsPending.value
  )
})

defineExpose({ form, isPending })
</script>

<template>
  <div class="w-full flex flex-col gap-[24px]">
    <Alert v-if="createTemplateIsError" variant="destructive" class="max-w-256 w-full mx-auto">
      <FeaturedIconOutline kind="outline" color="error" />

      <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
        t(`views.new-template.form.errors.title`)
      }}</AlertTitle>
      <AlertDescription>{{
        t(`api.new-template.errors.${createTemplateErrorCode}`)
      }}</AlertDescription>
    </Alert>

    <div class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-[2px]">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.new-template.form.sections.preview.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('views.new-template.form.sections.preview.subtitle') }}
        </h2>
      </div>

      <div v-if="desktopInfoIsPending" class="flex gap-2">
        <Skeleton class="h-16 w-47 rounded-l-2xl shrink-0" />
        <Skeleton class="h-16 w-full rounded-r-2xl" />
      </div>
      <div
        v-else
        class="grid gap-y-2 grid-flow-col"
        :style="{
          gridTemplateColumns:
            'var(--spacing-48) minmax(var(--spacing-48), var(--spacing-120)) auto'
        }"
      >
        <div class="grid grid-rows-subgrid row-span-3">
          <div
            class="row-start-2 w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover relative"
            :style="{
              backgroundImage: `url(${imageUrl})`
            }"
          >
            <Button
              class="absolute top-1 left-1 rounded-tl-xl"
              hierarchy="secondary-gray"
              size="sm"
              icon="image-plus"
            />
          </div>
        </div>

        <form class="contents" @submit.prevent="form.handleSubmit">
          <form.Field v-slot="{ field }" name="name" class="contents">
            <Field :data-invalid="isInvalid(field)" class="contents">
              <div class="text-sm font-semibold px-4">
                <FieldLabel :for="field.name">{{
                  t('views.new-template.form.sections.preview.fields.name.label')
                }}</FieldLabel>
              </div>
              <div
                class="w-full bg-base-white h-16 flex items-center border-gray-warm-200 px-4 border-y pr-0"
              >
                <InputField
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  :placeholder="
                    t('views.new-template.form.sections.preview.fields.name.placeholder')
                  "
                  :aria-invalid="isInvalid(field)"
                  :destructive="isInvalid(field)"
                  autocomplete="off"
                  type="text"
                  @blur="field.handleBlur"
                  @input="field.handleChange($event.target.value)"
                />
              </div>

              <div class="text-sm font-semibold px-4">
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </div>
            </Field>
          </form.Field>
          <form.Field v-slot="{ field }" name="description" class="contents">
            <Field :data-invalid="isInvalid(field)" class="contents">
              <div class="text-sm font-semibold px-4">
                <FieldLabel :for="field.name">{{
                  t('views.new-template.form.sections.preview.fields.description.label')
                }}</FieldLabel>
              </div>
              <div
                class="w-full bg-base-white h-16 flex items-center border-gray-warm-200 px-4 border-y rounded-r-2xl border-r"
              >
                <InputField
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  :placeholder="
                    t('views.new-template.form.sections.preview.fields.description.placeholder')
                  "
                  :aria-invalid="isInvalid(field)"
                  :destructive="isInvalid(field)"
                  autocomplete="off"
                  type="text"
                  @blur="field.handleBlur"
                  @input="field.handleChange($event.target.value)"
                />
              </div>

              <div class="text-sm font-semibold px-4">
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </div>
            </Field>
          </form.Field>
        </form>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="flex flex-col gap-[16px]">
        <div class="flex flex-col gap-0.5">
          <h1 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-template.form.sections.visibility.title') }}
          </h1>
          <h2 class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-template.form.sections.visibility.subtitle') }}
          </h2>
        </div>

        <form @submit.prevent="form.handleSubmit">
          <form.Field v-slot="{ field }" name="enabled" class="contents">
            <Field orientation="horizontal" :data-invalid="isInvalid(field)">
              <Switch
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :aria-invalid="isInvalid(field)"
                @update:model-value="field.handleChange"
              />
              <FieldContent>
                <FieldLabel :for="field.name">{{
                  t('views.new-template.form.sections.visibility.label')
                }}</FieldLabel>
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </FieldContent>
            </Field>
          </form.Field>
        </form>
      </div>
      <div class="flex flex-col gap-[16px]">
        <div class="flex flex-col gap-0.5">
          <h1 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-template.form.sections.alloweds.title') }}
          </h1>
          <i18n-t
            keypath="views.new-template.form.sections.alloweds.subtitle"
            tag="h2"
            class="text-sm font-regular text-gray-warm-700"
          >
            <template #groups>
              <b>{{ t('users.count.groups', 0) }}</b>
            </template>
            <template #users>
              <b>{{ t('users.count.users', 0) }}</b>
            </template>
          </i18n-t>
        </div>

        <div>
          <Button icon="plus" hierarchy="secondary-gray">{{
            t('views.new-template.form.sections.alloweds.button')
          }}</Button>
        </div>
      </div>
    </div>

    <div class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-[2px]">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.new-template.form.sections.hardware.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('views.new-template.form.sections.hardware.subtitle') }}
        </h2>
      </div>

      <Skeleton v-if="desktopInfoIsPending" class="h-48 w-full rounded-2xl" />
      <div v-else class="flex flex-col gap-0">
        <DomainAccessSummary
          class="border-b-0 rounded-b-none pb-0"
          :credentials="desktopDetails?.credentials"
          :viewers="desktopDetails?.viewers"
          :fullscreen="desktopDetails?.fullscreen"
        />
        <DomainHardwareSummary
          class="border-t-0 rounded-t-none"
          :vcpu="desktopDetails?.vcpu"
          :memory="desktopDetails?.memory"
          :disk-bus="desktopDetails?.disk_bus"
          :videos="desktopDetails?.videos.map((iface) => iface.name)"
          :interfaces="desktopDetails?.interfaces.map((iface) => iface.name)"
          :boot-order="desktopDetails?.boot_order.map((boot) => boot.name)"
          :isos="desktopDetails?.isos?.map((boot) => boot.name)"
          :floppies="desktopDetails?.floppies?.map((boot) => boot.name)"
          :loading="desktopDetailsIsPending"
          :vgpus="desktopDetails?.reservables?.vgpus"
        />
      </div>
    </div>
  </div>
</template>
