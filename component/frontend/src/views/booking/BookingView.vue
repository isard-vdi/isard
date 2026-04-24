<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import BookingCalendar from '@/components/booking/BookingCalendar.vue'
import type { CalendarView, CalendarSplit } from '@/components/booking/BookingCalendar.vue'
import BookingEventModal from '@/components/booking/BookingEventModal.vue'
import BookingStatusBar from '@/components/booking/BookingStatusBar.vue'
import { Button } from '@/components/ui/button'
import type { CalendarEvent } from '@/lib/booking/adapter'
import { canCreate as canCreateCheck, priorityAllowed } from '@/lib/booking/adapter'
import {
  formatAsDate,
  formatAsLocalDateTime,
  formatAsTime,
  localTimeToUtc,
  nextSunday,
  pastMonday
} from '@/lib/booking/date-utils'
import { useBookingStore, type BookingEventDraft } from '@/stores/booking'
import { useAuthStore } from '@/stores/auth'
import { useItemBookings } from '@/composables/useBookingCalendar'
import { useBookingPriority } from '@/composables/useBookingPriority'
import { useBookingMutations } from '@/composables/useBookingMutations'
import type { BookingItemType } from '@/lib/booking/constants'
import { describeApiError } from '@/lib/api-errors'

const route = useRoute()
const i18n = useI18n()
const { t } = i18n
const bookingStore = useBookingStore()
const authStore = useAuthStore()

const itemType = computed<Exclude<BookingItemType, 'all'>>(
  () => (route.params.type as 'desktop' | 'deployment') ?? 'desktop'
)
const itemId = computed(() => String(route.params.id ?? ''))

const initialStart = localTimeToUtc(formatAsLocalDateTime(pastMonday()))
const initialEnd = localTimeToUtc(formatAsLocalDateTime(nextSunday()))

bookingStore.setItem(itemId.value, itemType.value)
bookingStore.setView({
  timeframe: 'week',
  viewType: 'item',
  start: initialStart,
  end: initialEnd
})

const range = ref({ start: initialStart, end: initialEnd })
const returnType = ref<'all' | 'event'>('all')

const { events, isError } = useItemBookings(itemType, itemId, range, returnType)

const { priority, itemName } = useBookingPriority(itemId)
const { createEvent, editEvent, deleteEvent } = useBookingMutations()

const eventModalOpen = ref(false)
const modalMode = ref<'view' | 'edit' | 'create'>('create')
const modalDraft = ref<BookingEventDraft>({
  id: '',
  title: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: ''
})
const apiError = ref('')

let dragEnd = ''
let dragEndDate = ''
let dragEndTime = ''

const splitDays = ref<CalendarSplit[]>([
  {
    id: 1,
    label: t('components.bookings.item.split-labels.availability'),
    hide: false,
    class: 'split-availability'
  },
  {
    id: 2,
    label: t('components.bookings.item.split-labels.bookings'),
    hide: false,
    class: 'split-schedule'
  }
])

const calendarView = computed<CalendarView>(() => ({
  timeframe: bookingStore.view.timeframe,
  type: bookingStore.view.timeframe,
  viewType: bookingStore.view.viewType,
  itemType: bookingStore.itemType
}))

watch(
  () => bookingStore.view.timeframe,
  (timeframe) => {
    returnType.value = timeframe === 'month' ? 'event' : 'all'
    if (timeframe === 'month') splitDays.value[0].hide = true
  }
)

const hideSplit = (index: 0 | 1) => {
  if (bookingStore.view.timeframe === 'month') return
  splitDays.value[index].hide = !splitDays.value[index].hide
}

const onViewChanged = (event: Record<string, unknown>) => {
  const start = localTimeToUtc(String(event.startDate ?? event.firstCellDate ?? ''))
  const end = localTimeToUtc(String(event.endDate ?? event.lastCellDate ?? ''))
  const timeframe = (event.view as 'month' | 'week' | 'day') ?? bookingStore.view.timeframe
  bookingStore.setView({ timeframe, start, end })
  range.value = { start, end }
}

const onCellDragged = (event: Record<string, unknown>) => {
  const end = event.end as Date | string
  dragEnd = end instanceof Date ? end.toString() : String(end)
  dragEndDate = formatAsDate(dragEnd)
  dragEndTime = formatAsTime(dragEnd)
}

const openCreateModal = (start: Date | string, endDate = '', endTime = '') => {
  apiError.value = ''
  modalMode.value = 'create'
  modalDraft.value = {
    id: '',
    title: '',
    startDate: formatAsDate(start),
    startTime: formatAsTime(start),
    endDate,
    endTime
  }
  eventModalOpen.value = true
}

const onCellClicked = (event: Record<string, unknown>) => {
  const split = event.split as number | undefined
  if (split !== 2) {
    return
  }
  const raw = (event.date ?? event.start) as Date | string
  let start = raw instanceof Date ? raw : new Date(String(raw))
  if (start < new Date()) {
    start = new Date(Date.now() + 5 * 60_000)
  }
  const candidate = { start, end: dragEnd || undefined }
  const { allowed, error } = priorityAllowed(candidate, priority.value)
  const canCreate = canCreateCheck(candidate, events.value)
  if (!allowed) {
    apiError.value = error
    return
  }
  if (!canCreate) {
    apiError.value = t('messages.info.no-availability-event')
    return
  }
  openCreateModal(start, dragEndDate, dragEndTime)
  dragEnd = ''
  dragEndDate = ''
  dragEndTime = ''
}

const onEventClicked = (event: CalendarEvent) => {
  if (event.eventType === 'available' || event.eventType === 'overridable') return
  const mode: 'view' | 'edit' = new Date(event.end) > new Date() ? 'edit' : 'view'
  modalMode.value = mode
  apiError.value = ''
  modalDraft.value = {
    id: event.id,
    title: event.title,
    startDate: formatAsDate(event.start),
    startTime: formatAsTime(event.start),
    endDate: formatAsDate(event.end),
    endTime: formatAsTime(event.end)
  }
  eventModalOpen.value = true
}

const onAddBooking = () => {
  const start = new Date(Date.now() + 5 * 60_000)
  openCreateModal(start)
}

const onModalClose = () => {
  eventModalOpen.value = false
  apiError.value = ''
}

const draftToRange = (draft: BookingEventDraft) => ({
  start: new Date(`${draft.startDate}T${draft.startTime}`),
  end: new Date(`${draft.endDate}T${draft.endTime}`)
})

const onModalSubmit = (draft: BookingEventDraft) => {
  const { start, end } = draftToRange(draft)
  const { allowed, error } = priorityAllowed({ start, end }, priority.value)
  if (!allowed) {
    apiError.value = error
    return
  }
  const canCreate = canCreateCheck({ id: draft.id || undefined, start, end }, events.value)
  if (!canCreate) {
    apiError.value = t('messages.info.no-availability-event')
    return
  }
  if (modalMode.value === 'create') {
    createEvent.mutate(
      {
        body: {
          item_id: itemId.value,
          item_type: itemType.value,
          title: draft.title,
          start: start.toISOString(),
          end: end.toISOString()
        }
      },
      {
        onSuccess: () => {
          eventModalOpen.value = false
        },
        onError: (err: unknown) => {
          apiError.value = describeApiError(err, i18n, 'booking')
        }
      }
    )
  } else if (modalMode.value === 'edit') {
    editEvent.mutate(
      {
        path: { booking_id: draft.id },
        body: {
          title: draft.title,
          start: start.toISOString(),
          end: end.toISOString()
        }
      },
      {
        onSuccess: () => {
          eventModalOpen.value = false
        },
        onError: (err: unknown) => {
          apiError.value = describeApiError(err, i18n, 'booking')
        }
      }
    )
  }
}

const onModalDelete = (draft: BookingEventDraft) => {
  if (!draft.id) return
  deleteEvent.mutate(
    { path: { booking_id: draft.id } },
    {
      onSuccess: () => {
        eventModalOpen.value = false
      },
      onError: (err: unknown) => {
        apiError.value = (err as { message?: string })?.message ?? ''
      }
    }
  )
}

const showAvailabilitySplit = computed(() => {
  const role = authStore.user?.role_id
  const timeframe = bookingStore.view.timeframe
  if (timeframe === 'month' || bookingStore.view.viewType !== 'item') return false
  return role !== undefined
})
watch(
  showAvailabilitySplit,
  (show) => {
    splitDays.value[0].hide = !show
  },
  { immediate: true }
)

onUnmounted(() => {
  bookingStore.$reset()
})
</script>

<template>
  <div class="calendar-container">
    <div class="grid grid-cols-3 items-center mb-2 gap-2 px-2">
      <div class="flex flex-wrap gap-2">
        <Button hierarchy="secondary-gray" size="sm" @click="hideSplit(0)">
          <span
            class="inline-block w-2 h-2 rounded-full mr-2"
            :class="splitDays[0].hide ? 'bg-gray-warm-400/40' : ''"
            :style="splitDays[0].hide ? '' : 'background-color: rgba(255, 102, 102, 0.9)'"
          />
          {{ splitDays[0].label }}
        </Button>
        <Button hierarchy="secondary-gray" size="sm" @click="hideSplit(1)">
          <span
            class="inline-block w-2 h-2 rounded-full mr-2"
            :class="splitDays[1].hide ? 'bg-gray-warm-400/40' : ''"
            :style="splitDays[1].hide ? '' : 'background-color: rgba(100,200,255,.8)'"
          />
          {{ splitDays[1].label }}
        </Button>
      </div>
      <div class="text-center">
        <h4 class="text-2xl font-semibold">{{ itemName }}</h4>
      </div>
      <div />
    </div>
    <BookingStatusBar :priority="priority" @add-booking="onAddBooking" />
    <div class="calendar-row-container">
      <div v-if="isError" class="text-error-700">
        {{ t('api.loading-error') }}
      </div>
      <BookingCalendar
        v-else
        :disabled-split="1"
        :events="events"
        :split-days="splitDays"
        :view="calendarView"
        :snap-to-time="15"
        @view-changed="onViewChanged"
        @event-clicked="onEventClicked"
        @cell-clicked="onCellClicked"
        @cell-dragged="onCellDragged"
      />
    </div>
    <BookingEventModal
      :open="eventModalOpen"
      :mode="modalMode"
      :draft="modalDraft"
      :submitting="createEvent.isPending.value || editEvent.isPending.value"
      :deleting="deleteEvent.isPending.value"
      :api-error="apiError"
      @close="onModalClose"
      @submit="onModalSubmit"
      @delete="onModalDelete"
    />
  </div>
</template>

<style scoped>
.calendar-container {
  height: 100vh;
  width: 95%;
  padding: 1rem;
}
.calendar-row-container {
  height: calc(100vh - 15rem);
}
</style>

<style>
.vuecal__menu {
  background-color: transparent;
  border-bottom-color: #ced3d6;
  border-top-color: #ced3d6;
  border-right-color: transparent;
  border-left-color: transparent;
}
.vuecal__view-btn {
  background: none;
  padding: 0 10px;
  margin: 6px 4px;
  border-radius: 30px;
  height: 1.6rem;
  line-height: 20px;
  font-size: 0.9rem;
  text-transform: uppercase;
  border: none;
  color: inherit;
}
.vuecal__view-btn--active {
  background: #87ad69;
  color: #fff;
}
.vuecal__title-bar {
  background: #ced3d6;
}
.split-availability {
  color: #ed9a9a;
}
.split-schedule {
  color: #c0c4de;
}
.vuecal__cell .split-availability {
  background-color: #f1d5d5;
  color: rgba(0, 0, 0, 0.25);
  cursor: not-allowed;
}
.vuecal__now-line {
  color: rgb(143, 12, 12);
}
.vuecal__cell--selected {
  background-color: inherit !important;
}
.vuecal__cell--today {
  background-color: inherit !important;
}
.vuecal__time-cell {
  color: rgb(26, 25, 25) !important;
  margin-right: 0.2rem;
}
</style>
