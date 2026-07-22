<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'

import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
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

import { getEndTimeIntervals } from '@/lib/booking/end-time-intervals'

interface Props {
  open: boolean
  desktopId: string
  maxBookingDate?: string
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  maxBookingDate: undefined,
  submitting: false
})

const emit = defineEmits<{
  close: []
  submit: [payload: { desktopId: string; endTime: string }]
}>()

const { t, d } = useI18n()

const form = useForm({
  defaultValues: { end_time: '' },
  onSubmit: ({ value }) => {
    if (!value.end_time) return
    emit('submit', { desktopId: props.desktopId, endTime: value.end_time })
  }
})

watch(
  () => props.open,
  (open) => {
    if (open) form.reset()
  }
)

const endTimeIntervals = computed<Date[]>(() => {
  if (!props.maxBookingDate) return []
  return getEndTimeIntervals(new Date(props.maxBookingDate))
})

function isInvalid(field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}
</script>

<template>
  <Modal
    :open="props.open"
    class="pt-4 min-w-120"
    :title="t('components.desktop-start-now-modal.title')"
    :description="t('components.desktop-start-now-modal.description')"
    @close="emit('close')"
  >
    <form
      id="start-now-form"
      class="flex flex-row items-center gap-2 w-full mt-2"
      @submit.prevent.stop="form.handleSubmit"
    >
      <FieldGroup class="gap-4">
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
      </FieldGroup>
    </form>

    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t('components.desktop-start-now-modal.cancel')
      }}</Button>

      <Button hierarchy="primary" :disabled="props.submitting" type="submit" form="start-now-form">
        <Icon
          v-if="props.submitting"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        <Icon v-else name="play" stroke-color="currentColor" />
        {{ t('components.desktop-start-now-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
