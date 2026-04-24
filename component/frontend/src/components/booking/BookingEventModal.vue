<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useForm } from '@tanstack/vue-form'
import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { bookingEventSchema } from '@/lib/booking/schema'
import type { BookingEventDraft, BookingModalMode } from '@/stores/booking'

interface Props {
  open: boolean
  mode: BookingModalMode
  draft: BookingEventDraft
  submitting?: boolean
  deleting?: boolean
  apiError?: string
}

const props = withDefaults(defineProps<Props>(), {
  submitting: false,
  deleting: false,
  apiError: ''
})

const emit = defineEmits<{
  close: []
  submit: [draft: BookingEventDraft]
  delete: [draft: BookingEventDraft]
}>()

const { t } = useI18n()

const form = useForm({
  defaultValues: { ...props.draft },
  validators: { onChange: bookingEventSchema },
  onSubmit: ({ value }) => {
    emit('submit', { ...value })
  }
})

watch(
  () => [props.open, props.draft] as const,
  ([open]) => {
    if (open) form.reset({ ...props.draft })
  },
  { immediate: true }
)

const readOnly = computed(() => props.mode === 'view' || props.mode === 'edit')

const titleKey = computed(() => {
  const mode = props.mode === 'edit' ? 'view' : props.mode
  return `components.bookings.item.modal.${mode}.modal-title`
})

const submitLabelKey = computed(() => `components.bookings.item.modal.${props.mode}.button`)

function onDelete() {
  emit('delete', { ...form.state.values })
}

function fieldLabel(field: string): string {
  const labels: Record<string, string> = {
    startDate: t('components.bookings.item.modal.start-date'),
    startTime: t('components.bookings.item.modal.start-time'),
    endDate: t('components.bookings.item.modal.end-date'),
    endTime: t('components.bookings.item.modal.end-time'),
    title: t('components.bookings.item.modal.title')
  }
  return labels[field] ?? field
}

function fieldErrorText(field: string, errors: readonly unknown[]): string {
  if (!errors.length) return ''
  const first = errors[0] as { message?: string } | string | undefined
  const code = typeof first === 'string' ? first : first?.message
  if (!code) return ''
  const customKeys = ['past-booking', 'end-before-start', 'minimum-time']
  if (customKeys.includes(code)) {
    return t(`components.bookings.errors.${code}`)
  }
  return t(`validations.${code}`, { property: fieldLabel(field) })
}

function isInvalid(errors: readonly unknown[]): boolean {
  return errors.length > 0
}
</script>

<template>
  <Modal :open="props.open" size="lg" :title="t(titleKey)" @close="emit('close')">
    <form
      id="booking-event-form"
      class="grid grid-cols-2 gap-4 pt-2 pb-4"
      @submit.prevent.stop="form.handleSubmit"
    >
      <form.Field name="title">
        <template #default="{ field }">
          <div class="col-span-2">
            <Label for="title">{{ t('components.bookings.item.modal.title') }}</Label>
            <Input
              id="title"
              :model-value="field.state.value"
              :disabled="readOnly"
              placeholder="Enter a title"
              @update:model-value="(v) => field.handleChange(String(v ?? ''))"
            />
          </div>
        </template>
      </form.Field>
      <form.Field name="startDate">
        <template #default="{ field }">
          <div>
            <Label for="startDate">{{ t('components.bookings.item.modal.start-date') }}*</Label>
            <Input
              id="startDate"
              type="date"
              :model-value="field.state.value"
              :disabled="readOnly"
              :data-invalid="isInvalid(field.state.meta.errors)"
              @update:model-value="(v) => field.handleChange(String(v ?? ''))"
            />
            <p v-if="isInvalid(field.state.meta.errors)" class="text-error-700 text-xs mt-1">
              {{ fieldErrorText('startDate', field.state.meta.errors) }}
            </p>
          </div>
        </template>
      </form.Field>
      <form.Field name="startTime">
        <template #default="{ field }">
          <div>
            <Label for="startTime">{{ t('components.bookings.item.modal.start-time') }}*</Label>
            <Input
              id="startTime"
              type="time"
              :model-value="field.state.value"
              :disabled="readOnly"
              :data-invalid="isInvalid(field.state.meta.errors)"
              @update:model-value="(v) => field.handleChange(String(v ?? ''))"
            />
            <p v-if="isInvalid(field.state.meta.errors)" class="text-error-700 text-xs mt-1">
              {{ fieldErrorText('startTime', field.state.meta.errors) }}
            </p>
          </div>
        </template>
      </form.Field>
      <form.Field name="endDate">
        <template #default="{ field }">
          <div>
            <Label for="endDate">{{ t('components.bookings.item.modal.end-date') }}*</Label>
            <Input
              id="endDate"
              type="date"
              :model-value="field.state.value"
              :disabled="readOnly"
              :data-invalid="isInvalid(field.state.meta.errors)"
              @update:model-value="(v) => field.handleChange(String(v ?? ''))"
            />
            <p v-if="isInvalid(field.state.meta.errors)" class="text-error-700 text-xs mt-1">
              {{ fieldErrorText('endDate', field.state.meta.errors) }}
            </p>
          </div>
        </template>
      </form.Field>
      <form.Field name="endTime">
        <template #default="{ field }">
          <div>
            <Label for="endTime">{{ t('components.bookings.item.modal.end-time') }}*</Label>
            <Input
              id="endTime"
              type="time"
              :model-value="field.state.value"
              :disabled="readOnly"
              :data-invalid="isInvalid(field.state.meta.errors)"
              @update:model-value="(v) => field.handleChange(String(v ?? ''))"
            />
            <p v-if="isInvalid(field.state.meta.errors)" class="text-error-700 text-xs mt-1">
              {{ fieldErrorText('endTime', field.state.meta.errors) }}
            </p>
          </div>
        </template>
      </form.Field>
      <div v-if="props.apiError" class="col-span-2 text-error-700 text-sm">
        {{ props.apiError }}
      </div>
    </form>
    <template #footer>
      <div class="w-full flex justify-between">
        <Button
          v-if="props.mode === 'edit'"
          hierarchy="destructive"
          :disabled="props.deleting"
          @click="onDelete"
        >
          {{ t('components.bookings.item.modal.delete.button') }}
        </Button>
        <div class="ml-auto flex gap-2">
          <Button hierarchy="link-gray" @click="emit('close')">
            {{ t('components.bookings.item.modal.cancel') }}
          </Button>
          <Button
            v-if="props.mode === 'create'"
            hierarchy="primary"
            type="submit"
            form="booking-event-form"
            :disabled="props.submitting"
          >
            {{ t(submitLabelKey) }}
          </Button>
        </div>
      </div>
    </template>
  </Modal>
</template>
