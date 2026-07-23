<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Icon } from '@/components/icon'
import { Modal } from '@/components/modal'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

import type { AvailableReservablesResponse } from '@/gen/oas/apiv4'
import { earliestBookingDate, getEndTimeIntervals } from '@/lib/booking/end-time-intervals'
import { MAX_VGPU_PROFILES } from '@/lib/vgpuSelection'

interface Props {
  open: boolean
  desktopId: string
  currentProfileIds?: string[]
  availableReservables?: AvailableReservablesResponse | null
  isLoadingReservables?: boolean
  submitting?: boolean
  submitError?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  currentProfileIds: () => [],
  availableReservables: null,
  isLoadingReservables: false,
  submitting: false,
  submitError: null
})

const emit = defineEmits<{
  close: []
  submit: [payload: { desktopId: string; profileIds: string[]; endTime: string }]
}>()

const { t, d } = useI18n()

const form = useForm({
  defaultValues: { profiles: [] as string[], end_time: '' },
  onSubmit: ({ value }) => {
    if (!value.profiles.length || !value.end_time) return
    emit('submit', {
      desktopId: props.desktopId,
      profileIds: value.profiles,
      endTime: value.end_time
    })
  }
})

const selectedProfiles = form.useStore((state) => state.values.profiles)
const availableProfiles = computed(() => props.availableReservables?.reservables_available ?? [])

const seeded = ref(false)

watch(
  () => props.open,
  (open) => {
    if (open) {
      form.reset()
      seeded.value = false
    }
  }
)

watch(availableProfiles, (profiles) => {
  if (!props.open || seeded.value || !profiles.length) return
  seeded.value = true
  const availableIds = new Set(profiles.map((p) => p.id))
  form.setFieldValue(
    'profiles',
    props.currentProfileIds.filter((id) => availableIds.has(id))
  )
})

const isProfileDisabled = (id: string): boolean =>
  !selectedProfiles.value.includes(id) && selectedProfiles.value.length >= MAX_VGPU_PROFILES

const endLimit = computed(() =>
  earliestBookingDate(availableProfiles.value, selectedProfiles.value)
)
const endTimeIntervals = computed<Date[]>(() =>
  endLimit.value ? getEndTimeIntervals(endLimit.value) : []
)

watch(endLimit, (limit) => {
  const current = form.state.values.end_time
  if (!current) return
  if (!limit || new Date(current).getTime() > limit.getTime()) {
    form.setFieldValue('end_time', '')
  }
})

const submitErrorMessage = computed(() => {
  if (!props.submitError) return null
  return t(
    `components.desktop-gpu-change-and-start-modal.errors.${props.submitError}`,
    `components.desktop-gpu-change-and-start-modal.errors.generic`
  )
})

function isInvalid(field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}
</script>

<template>
  <Modal
    v-if="props.open"
    :open="props.open"
    class="pt-4 min-w-120"
    :title="t('components.desktop-gpu-change-and-start-modal.title')"
    @close="emit('close')"
  >
    <div class="mt-4 flex flex-col gap-4">
      {{ t('components.desktop-gpu-change-and-start-modal.description') }}

      <Alert v-if="submitErrorMessage" variant="destructive">
        <AlertTitle>{{
          t('components.desktop-gpu-change-and-start-modal.errors.title')
        }}</AlertTitle>
        <AlertDescription>{{ submitErrorMessage }}</AlertDescription>
      </Alert>

      <div
        v-if="props.isLoadingReservables"
        class="w-full flex flex-col items-start justify-start gap-2"
      >
        <Skeleton class="h-4 w-1/4" />
        <Skeleton class="h-8 w-full" />
      </div>

      <Empty v-else-if="!props.availableReservables" class="gap-2">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none">
            <Icon name="alert-triangle" class="size-12" stroke-color="warning-600" />
          </EmptyMedia>
        </EmptyHeader>
        <EmptyTitle class="font-semibold">{{
          t('components.desktop-gpu-change-and-start-modal.empty.title')
        }}</EmptyTitle>
        <EmptyDescription>{{
          t('components.desktop-gpu-change-and-start-modal.empty.description', {
            kind: t('domains.desktops', 0)
          })
        }}</EmptyDescription>
      </Empty>

      <form
        v-else
        id="change-and-start-form"
        class="flex flex-row items-center gap-2 w-full"
        @submit.prevent.stop="form.handleSubmit"
      >
        <FieldGroup class="gap-4">
          <form.Field name="profiles">
            <template #default="{ field }">
              <Field :data-invalid="isInvalid(field)">
                <FieldLabel :for="field.name">{{
                  t('components.desktop-gpu-change-and-start-modal.gpu-select.label')
                }}</FieldLabel>
                <Select
                  :id="field.name"
                  :name="field.name"
                  :aria-invalid="isInvalid(field)"
                  class="w-full"
                  multiple
                  :model-value="field.state.value ?? []"
                  @update:model-value="(value) => field.handleChange((value as string[]) ?? [])"
                >
                  <SelectTrigger size="default" class="bg-base-white">
                    <SelectValue
                      :placeholder="
                        t('components.desktop-gpu-change-and-start-modal.gpu-select.placeholder')
                      "
                    />
                  </SelectTrigger>
                  <SelectContent class="left-0 right-0">
                    <SelectGroup>
                      <SelectItem
                        v-for="profile in availableProfiles"
                        :key="profile.id"
                        :value="profile.id"
                        :disabled="isProfileDisabled(profile.id)"
                      >
                        {{ profile.name }}
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>

                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </Field>
            </template>
          </form.Field>

          <template v-if="selectedProfiles.length">
            <form.Field name="end_time">
              <template #default="{ field }">
                <Field :data-invalid="isInvalid(field)">
                  <FieldLabel :for="field.name">{{
                    t('components.desktop-start-now-modal.select.label')
                  }}</FieldLabel>

                  <Select
                    :id="field.name"
                    :name="field.name"
                    :aria-invalid="isInvalid(field)"
                    class="w-full"
                    :model-value="field.state.value"
                    @update:model-value="field.handleChange($event?.toString() || '')"
                  >
                    <SelectTrigger size="default" class="bg-base-white">
                      <SelectValue
                        :placeholder="t('components.desktop-start-now-modal.select.placeholder')"
                      />
                    </SelectTrigger>
                    <SelectContent class="left-0 right-0">
                      <SelectGroup>
                        <SelectItem
                          v-for="endTime in endTimeIntervals"
                          :key="endTime.toISOString()"
                          :value="endTime.toISOString()"
                        >
                          {{ d(endTime, { timeStyle: 'short' }) }}
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
              </template>
            </form.Field>
          </template>
        </FieldGroup>
      </form>
    </div>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t('components.desktop-gpu-change-and-start-modal.cancel')
      }}</Button>

      <Button
        hierarchy="primary"
        :disabled="props.submitting"
        type="submit"
        form="change-and-start-form"
      >
        <Icon
          v-if="props.submitting"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        <Icon v-else name="play" stroke-color="currentColor" />
        {{ t('components.desktop-gpu-change-and-start-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
