<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

import {
  getTemplateInfoApiV4ItemTemplateTemplateIdGetInfoGetOptions,
  getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGetOptions,
  duplicateTemplateApiV4ItemTemplateTemplateIdDuplicatePostMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ErrorResponse } from '@/gen/oas/apiv4'
import { checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import DomainAccessSummary from '@/components/domain/DomainAccessSummary.vue'
import DomainHardwareSummary from '@/components/domain/DomainHardwareSummary.vue'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { InputField } from '@/components/input-field'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// --------------------------------------------------
// Quota check
// --------------------------------------------------

const quotaQuery = useQuery({
  ...checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const quotaCheckPassed = computed(() => quotaQuery.isSuccess.value)

// --------------------------------------------------

const templateId = ref<string>(route.params.templateId as string)

const { data: templateInfo, isPending: templateInfoIsPending } = useQuery(
  getTemplateInfoApiV4ItemTemplateTemplateIdGetInfoGetOptions({
    path: {
      template_id: templateId.value
    }
  })
)
const { data: templateDetails, isPending: templateDetailsIsPending } = useQuery(
  getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGetOptions({
    path: {
      template_id: templateId.value
    }
  })
)

const imageUrl = computed(() => {
  return templateInfo.value?.image?.url || ''
})

const duplicateTemplateErrorCode = ref<string | undefined>(undefined)
const {
  mutate: duplicateTemplate,
  mutateAsync: duplicateTemplateAsync,
  isPending: duplicateTemplateIsPending,
  isError: duplicateTemplateIsError,
  error: duplicateTemplateError,
  data: duplicateTemplateData
} = useMutation({
  ...duplicateTemplateApiV4ItemTemplateTemplateIdDuplicatePostMutation(),
  onSuccess: (data) => {
    router.push({ name: 'templates', params: { templateId: data.id } })
  },
  onError: (error: any) => {
    const errorResponse = JSON.parse(error.message) as ErrorResponse
    duplicateTemplateErrorCode.value = errorResponse.description_code

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
    name: computed(() => templateInfo.value?.name || ''),
    description: computed(() => templateInfo.value?.description || ''),
    enabled: true
  }),
  validators: {
    onChange: formSchema
  },
  onSubmit: ({ value }) => {
    duplicateTemplateAsync({
      path: {
        template_id: templateId.value
      },
      body: {
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
    templateInfoIsPending.value ||
    templateDetailsIsPending.value ||
    duplicateTemplateIsPending.value
  )
})
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="quotaQuery.isError.value"
    :title="t('components.templates.quota-exceeded-modal.title')"
    :description="t('components.templates.quota-exceeded-modal.description')"
    :cancel-label="t('components.templates.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'templates' }"
  />

  <template v-if="quotaCheckPassed">
    <div
      class="flex flex-col-reverse md:flex-row items-start justify-between max-w-480 w-full mx-auto mb-8 gap-4"
    >
      <div class="flex flex-col gap-1">
        <h1 class="text-lg font-bold text-gray-warm-900">
          {{ t('views.new-template.form.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('views.new-template.form.subtitle') }}
        </h2>
      </div>

      <div class="flex gap-4 md:w-auto w-full justify-end">
        <Button :as="RouterLink" :to="{ name: 'templates' }" hierarchy="link-color">{{
          t('views.new-template.header.cancel')
        }}</Button>

        <form.Subscribe v-slot="{ isValid, isSubmitting }">
          <Button
            type="submit"
            :disabled="!isValid || isPending"
            :icon="isSubmitting || isPending ? 'loading-02' : ''"
            icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
            @click="form.handleSubmit"
            >{{ t('views.new-template.header.create-template') }}</Button
          >
        </form.Subscribe>
      </div>
    </div>

    <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
      <div class="w-full flex flex-col gap-[24px]">
        <Alert
          v-if="duplicateTemplateIsError"
          variant="destructive"
          class="max-w-256 w-full mx-auto"
        >
          <FeaturedIconOutline kind="outline" color="error" />

          <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
            t(`views.new-template.form.errors.title`)
          }}</AlertTitle>
          <AlertDescription>{{
            t(`api.new-template.errors.${duplicateTemplateErrorCode}`)
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

          <div v-if="templateInfoIsPending" class="flex gap-2">
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

          <Skeleton v-if="templateDetailsIsPending" class="h-48 w-full rounded-2xl" />
          <div v-else class="flex flex-col gap-0">
            <DomainAccessSummary
              class="border-b-0 rounded-b-none pb-0"
              :credentials="templateDetails?.credentials as any"
              :viewers="templateDetails?.viewers"
              :fullscreen="templateDetails?.fullscreen"
            />
            <DomainHardwareSummary
              class="border-t-0 rounded-t-none"
              :vcpu="templateDetails?.vcpu"
              :memory="templateDetails?.memory"
              :disk-bus="templateDetails?.disk_bus"
              :videos="templateDetails?.videos.map((iface) => iface.name)"
              :interfaces="templateDetails?.interfaces.map((iface) => iface.name)"
              :boot-order="templateDetails?.boot_order.map((boot) => boot.name)"
              :isos="templateDetails?.isos?.map((boot) => boot.name)"
              :floppies="templateDetails?.floppies?.map((boot) => boot.name)"
              :loading="templateDetailsIsPending"
              :vgpus="templateDetails?.reservables?.vgpus"
            />
          </div>
        </div>
      </div>
    </main>
  </template>
</template>
