<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import type * as z from 'zod'
import { getTemplateNonpersistentDesktopOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useUserStore } from '@/stores/user'
import { useDomainInfoForm, type DomainInfoSource } from '@/composables/useDomainInfoForm'
import { CheckboxGroup } from '@/components/checkbox-group'
import type { FeaturedIconItem } from '@/components/checkbox-group/featured-icon'
import { DesktopCardBase, DesktopCardHeader, DesktopCardSkeleton } from '@/components/desktop-card'
import { InputField } from '@/components/input-field'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export type DomainKind = 'persistent' | 'nonpersistent' | 'deployment'
export type DomainInfoPreview = 'desktop-card' | 'template-row'

const props = withDefaults(
  defineProps<{
    loading?: boolean
    source?: DomainInfoSource
    extraDefaults?: Record<string, string>
    extraSchema?: z.ZodRawShape
    imageUrl?: string
    templateId?: string
    showKindSelector?: boolean
    kind?: DomainKind
    persistentQuotaExceeded?: boolean
    temporalQuotaExceeded?: boolean
    entity?: 'desktops' | 'templates'
    preview?: DomainInfoPreview
  }>(),
  {
    loading: false,
    source: undefined,
    extraDefaults: undefined,
    extraSchema: undefined,
    imageUrl: '',
    templateId: undefined,
    showKindSelector: false,
    kind: 'persistent',
    persistentQuotaExceeded: false,
    temporalQuotaExceeded: false,
    entity: 'desktops',
    preview: 'desktop-card'
  }
)

const emit = defineEmits<{
  'change-image': []
  'update:kind': [kind: 'persistent' | 'nonpersistent']
}>()

const { t } = useI18n()
const userStore = useUserStore()

const { form, values, isDirty, isValid } = useDomainInfoForm({
  source: () => props.source,
  extraDefaults: props.extraDefaults,
  extraSchema: props.extraSchema
})

const kindModel = computed({
  get: () => (props.kind === 'nonpersistent' ? 'nonpersistent' : 'persistent'),
  set: (value: 'persistent' | 'nonpersistent') => emit('update:kind', value)
})

// TODO(old-frontend-removal): this block, the temporal option's note/disabled/
// tooltip and the `single-temporal` locale keys go with the old frontend, whose
// one-desktop-per-template card is the only reason the backend reuses.
const singleTemporalPerTemplate = computed(
  () => props.showKindSelector && !userStore.config?.multiple_temporal_desktops
)

// Only asked where that limit applies: elsewhere the endpoint always answers null.
const { data: reusedTemporalDesktop } = useQuery({
  ...getTemplateNonpersistentDesktopOptions({
    path: { template_id: props.templateId || '' }
  }),
  enabled: computed(() => singleTemporalPerTemplate.value && !!props.templateId)
})

const temporalDisabled = computed(() => !!reusedTemporalDesktop.value?.desktop_id)

const kindOptions = computed<FeaturedIconItem[]>(() => {
  const quotaTooltip = (kind: 'persistent' | 'temporal') => ({
    title: t('components.domain.configuration.quota-exceeded.title'),
    description: t(`components.domain.configuration.quota-exceeded.${kind}`)
  })

  const options: FeaturedIconItem[] = [
    {
      color: 'persistent',
      title: t('components.domain.configuration.kind.persistent.title'),
      description: t('components.domain.configuration.kind.persistent.description'),
      value: 'persistent',
      disabled: props.persistentQuotaExceeded,
      tooltip: props.persistentQuotaExceeded ? quotaTooltip('persistent') : undefined
    }
  ]

  if (userStore.config?.show_temporal_tab ?? true) {
    options.push({
      color: 'temporary',
      title: t('components.domain.configuration.kind.nonpersistent.title'),
      description: t('components.domain.configuration.kind.nonpersistent.description'),
      value: 'nonpersistent',
      // TODO(old-frontend-removal): note, disabled and tooltip, with their
      // `components.domain.configuration.single-temporal.*` locale keys.
      note: singleTemporalPerTemplate.value
        ? t('components.domain.configuration.single-temporal.description')
        : undefined,
      disabled: temporalDisabled.value || props.temporalQuotaExceeded,
      tooltip: props.temporalQuotaExceeded
        ? quotaTooltip('temporal')
        : temporalDisabled.value
          ? {
              title: t('components.domain.configuration.single-temporal.title'),
              description: t('components.domain.configuration.single-temporal.existing')
            }
          : undefined
    })
  }

  return options
})

// Quota and the reuse query both land late: never sit on a locked kind.
watch(
  kindOptions,
  (options) => {
    if (!props.showKindSelector) return
    if (!options.find((option) => option.value === kindModel.value)?.disabled) return
    const available = options.find((option) => !option.disabled)
    if (available) {
      emit('update:kind', available.value as 'persistent' | 'nonpersistent')
    }
  },
  { immediate: true }
)

const isInvalid = (field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) =>
  field.state.meta.isTouched && !field.state.meta.isValid

defineExpose({
  form,
  values,
  isDirty,
  isValid,
  getFormData: () => ({ ...values.value }),
  reset: () => form.reset()
})
</script>

<template>
  <!-- Templates keep the compact strip shared with the create/duplicate forms. -->
  <div v-if="preview === 'template-row'" class="flex flex-col gap-4">
    <div class="flex flex-col">
      <h2 class="text-lg font-semibold text-gray-warm-900">
        {{ t('views.new-template.form.sections.preview.title') }}
      </h2>
      <p class="text-sm font-regular text-gray-warm-700">
        {{ t('views.new-template.form.sections.preview.subtitle') }}
      </p>
    </div>

    <div v-if="loading" class="flex gap-2">
      <Skeleton class="h-16 w-47 rounded-l-2xl shrink-0" />
      <Skeleton class="h-16 w-full rounded-r-2xl" />
    </div>
    <div
      v-else
      class="grid gap-y-2 grid-flow-col"
      :style="{
        gridTemplateColumns: 'var(--spacing-48) minmax(var(--spacing-48), var(--spacing-120)) auto'
      }"
    >
      <div class="grid grid-rows-subgrid row-span-3">
        <div
          class="row-start-2 w-48 h-16 overflow-hidden shrink-0 rounded-l-2xl object-cover bg-center bg-cover relative"
          :style="{ backgroundImage: imageUrl ? `url(${imageUrl})` : undefined }"
        >
          <Button
            class="absolute top-1 left-1 rounded-tl-xl"
            hierarchy="secondary-gray"
            size="sm"
            icon="image-plus"
            :aria-label="t('components.change-image-modal.title')"
            @click="emit('change-image')"
          />
        </div>
      </div>

      <form class="contents" @submit.prevent>
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
                :placeholder="t('views.new-template.form.sections.preview.fields.name.placeholder')"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                autocomplete="off"
                type="text"
                maxlength="50"
                @blur="field.handleBlur"
                @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
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
                maxlength="255"
                @blur="field.handleBlur"
                @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="text-sm font-semibold px-4">
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </div>
          </Field>
        </form.Field>
      </form>
    </div>

    <slot name="extra" :form="form" />
  </div>

  <div v-else class="flex flex-col flex-col-reverse lg:flex-row justify-center gap-12">
    <div class="flex-1">
      <h3 class="text-lg font-semibold text-gray-warm-900">
        {{ t('components.domain.configuration.preview.title') }}
      </h3>
      <p class="text-sm font-regular mb-6">
        {{ t('components.domain.configuration.preview.description') }}
      </p>
      <DesktopCardSkeleton v-if="loading" class="w-[520px] h-[370px]" />
      <DesktopCardBase v-else :image-url="imageUrl" :desktop-kind="kind">
        <template #header-actions>
          <Button
            icon="image-plus"
            hierarchy="secondary-gray"
            size="sm"
            :aria-label="t('components.change-image-modal.title')"
            @click="emit('change-image')"
          />
        </template>
        <template #header>
          <DesktopCardHeader :name="values.name" :description="values.description" />
        </template>
        <template #footer>
          <Tooltip>
            <TooltipTrigger as-child>
              <span
                role="button"
                aria-disabled="true"
                tabindex="0"
                :aria-label="t('components.desktops.desktop-card.status.stopped.action')"
                class="inline-flex shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand"
              >
                <Button
                  icon="play"
                  icon-class="fill-current"
                  hierarchy="secondary-color"
                  size="sm"
                  class="shrink-0"
                  disabled
                >
                  {{ t('components.desktops.desktop-card.status.stopped.action') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent
              :title="t('components.domain.configuration.preview.start-disabled')"
              side="top"
            />
          </Tooltip>
        </template>
      </DesktopCardBase>
    </div>
    <div class="flex-1">
      <div v-if="showKindSelector" class="mb-6">
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.domain.configuration.kind.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('components.domain.configuration.kind.description') }}
        </p>
        <CheckboxGroup
          v-model="kindModel"
          :items="kindOptions"
          kind="featured-icon"
          type="single"
          check-type="radio"
          direction="flex-row"
          :hide-description="true"
        />
      </div>
      <div>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t(`components.domain.configuration.info.title.${entity}`) }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t(`components.domain.configuration.info.description.${entity}`) }}
        </p>
        <!-- Skeletons until loaded: the first edit snapshots every value, so a
             field still reading its unresolved seed would be frozen empty. -->
        <div v-if="loading" class="flex flex-col gap-3">
          <Skeleton class="h-11 w-full" />
          <Skeleton class="h-25 w-full" />
        </div>
        <div v-else class="flex flex-col gap-3">
          <form.Field v-slot="{ field }" name="name">
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :aria-label="t('components.domain.info.name.label')"
              :placeholder="t('components.domain.info.name.placeholder')"
              maxlength="50"
              autofocus
              @update:model-value="(value) => field.handleChange(String(value))"
              @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
              @blur="field.handleBlur"
            />
          </form.Field>
          <form.Field v-slot="{ field }" name="description">
            <Textarea
              :model-value="field.state.value"
              maxlength="255"
              class="bg-base-white resize-none h-25"
              :aria-label="t('components.domain.info.description.label')"
              :placeholder="t('components.domain.info.description.placeholder')"
              @update:model-value="(value) => field.handleChange(String(value))"
            />
          </form.Field>
          <slot name="extra" :form="form" />
        </div>
      </div>
    </div>
  </div>
</template>
