<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BookingCalendar from '@/components/booking/BookingCalendar.vue'
import type { CalendarView } from '@/components/booking/BookingCalendar.vue'
import type { CalendarEvent } from '@/lib/booking/adapter'
import {
  localTimeToUtc,
  pastMonday,
  nextSunday,
  formatAsLocalDateTime
} from '@/lib/booking/date-utils'
import { useBookingsSummary } from '@/composables/useBookingCalendar'
import { useBookingStore } from '@/stores/booking'

const { t } = useI18n()
const bookingStore = useBookingStore()

const initialStart = localTimeToUtc(formatAsLocalDateTime(pastMonday()))
const initialEnd = localTimeToUtc(formatAsLocalDateTime(nextSunday()))

bookingStore.setItem(null, 'all')
bookingStore.setView({
  timeframe: 'week',
  viewType: 'summary',
  start: initialStart,
  end: initialEnd
})

const range = ref({ start: initialStart, end: initialEnd })

const { events, isPending, isError } = useBookingsSummary(range)

const calendarView = computed<CalendarView>(() => ({
  timeframe: bookingStore.view.timeframe,
  type: bookingStore.view.timeframe,
  viewType: bookingStore.view.viewType
}))

const onViewChanged = (event: Record<string, unknown>) => {
  const start = localTimeToUtc(String(event.startDate ?? event.firstCellDate ?? ''))
  const end = localTimeToUtc(String(event.endDate ?? event.lastCellDate ?? ''))
  const timeframe = (event.view as 'month' | 'week' | 'day') ?? bookingStore.view.timeframe
  bookingStore.setView({ timeframe, start, end })
  range.value = { start, end }
}

const onEventClicked = (_event: CalendarEvent) => {
  // Modal flows arrive in Phase 2. Summary stays read-only, matching Vue 2.
}

const onCellDragged = (_event: Record<string, unknown>) => {
  // Read-only in summary view.
}

watch(
  () => bookingStore.view,
  () => {
    /* Keep store view in sync; consumed by watchers elsewhere. */
  },
  { deep: true }
)
</script>

<template>
  <div class="calendar-container">
    <div class="text-center mb-4">
      <h4 class="text-2xl font-semibold">
        {{ t('components.bookings.summary.title') }}
      </h4>
    </div>
    <div class="calendar-row-container">
      <div v-if="isError" class="text-error-700">
        {{ t('api.loading-error') }}
      </div>
      <BookingCalendar
        v-else
        :disabled-split="1"
        :events="events"
        :view="calendarView"
        :snap-to-time="15"
        @view-changed="onViewChanged"
        @event-clicked="onEventClicked"
        @cell-dragged="onCellDragged"
      />
      <div v-if="isPending" class="text-gray-warm-500 text-sm mt-2">
        {{ t('api.loading') }}
      </div>
    </div>
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

.weekday-label {
  margin: 0.1rem;
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
