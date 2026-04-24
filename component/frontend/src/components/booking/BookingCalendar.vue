<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import VueCal from 'vue-cal'
import 'vue-cal/dist/vuecal.css'
import 'vue-cal/dist/i18n/es.es.js'
import 'vue-cal/dist/i18n/ca.es.js'
import 'vue-cal/dist/i18n/de.es.js'
import 'vue-cal/dist/i18n/fr.es.js'
import 'vue-cal/dist/i18n/ru.es.js'
import type { CalendarEvent } from '@/lib/booking/adapter'

export interface CalendarSplit {
  id: number
  label: string
  hide?: boolean
  class?: string
  color?: string
}

export interface CalendarView {
  timeframe?: string
  type?: string
  viewType?: string
  itemType?: string
  start?: string
  end?: string
}

interface Props {
  events: CalendarEvent[]
  splitDays?: CalendarSplit[]
  disabledSplit?: number
  view: CalendarView
  timeFrom?: number
  timeTo?: number
  snapToTime?: number
}

const props = withDefaults(defineProps<Props>(), {
  splitDays: () => [],
  disabledSplit: undefined,
  timeFrom: 0,
  timeTo: 24,
  snapToTime: 15
})

const emit = defineEmits<{
  viewChanged: [event: Record<string, unknown>]
  eventCreated: [event: Record<string, unknown>]
  cellClicked: [event: Record<string, unknown>]
  cellDragged: [event: Record<string, unknown>]
  eventClicked: [event: CalendarEvent, e?: Event]
  eventDblClicked: [event: CalendarEvent, e?: Event]
}>()

const { locale } = useI18n()

const calLocale = computed(() => {
  const short = locale.value.split('-')[0]
  return short === 'eu' ? 'en' : short
})

const onViewChange = (event: Record<string, unknown>) => {
  ;(event as { startDate: unknown }).startDate = (event as { firstCellDate: unknown }).firstCellDate
  emit('viewChanged', event)
}

const onEventCreate = (event: Record<string, unknown>) => {
  if (props.disabledSplit !== undefined && event.split === props.disabledSplit) {
    return false
  }
  emit('eventCreated', event)
  return event
}

const onCellClick = (event: Record<string, unknown>) => emit('cellClicked', event)
const onCellDrag = (event: Record<string, unknown>) => emit('cellDragged', event)
const onEventClick = (event: CalendarEvent, e?: Event) => emit('eventClicked', event, e)

const scrollToCurrentTime = () => {
  const calendar = document.querySelector('#vuecal .vuecal__bg')
  if (!calendar) return
  const hours = 9 - props.timeFrom
  calendar.scrollTo({ top: hours * 40, behavior: 'smooth' })
}
</script>

<template>
  <vue-cal
    id="vuecal"
    sticky-split-labels
    today-button
    :locale="calLocale"
    :events="props.events"
    :disable-views="['years', 'year']"
    :split-days="props.splitDays"
    :time-from="props.timeFrom * 60"
    :time-to="props.timeTo * 60"
    events-on-month-view="short"
    :snap-to-time="props.snapToTime"
    :on-event-click="onEventClick"
    :editable-events="{ title: false, drag: false, resize: false, delete: false, create: true }"
    :on-event-create="onEventCreate"
    :time-cell-height="40"
    :min-event-width="50"
    @cell-click="onCellClick"
    @view-change="onViewChange"
    @event-drag-create="onCellDrag"
    @ready="scrollToCurrentTime"
  >
    <template #split-label="{ split }">
      <i v-if="split.id === 2" class="icon material-icons">person</i>
      <i v-else class="icon material-icons">event</i>
      <strong :style="`color: ${split.color}`">{{ split.label }}</strong>
    </template>
    <template #event="{ event, view: slotView }">
      <div :title="event.title">
        <div v-if="slotView.id === 'month'">
          <span>
            {{ event.start.formatTime('HH:mm') }} - {{ event.end.formatTime('HH:mm') }}
            {{ event.title }}
          </span>
        </div>
        <div v-else>
          <small>
            {{ event.start.formatTime('HH:mm') }} - {{ event.end.formatTime('HH:mm') }}
          </small>
          <h6>{{ event.title }}</h6>
          <small v-if="event.subtitle">{{ event.subtitle }}</small>
        </div>
      </div>
    </template>
  </vue-cal>
</template>

<style>
.vuecal__menu,
.vuecal__cell-events-count {
  background-color: #4fb2f3;
  border: 1px solid #5a5a5a;
}
.vuecal__title-bar {
  background-color: #368ec8;
}

.vuecal__cell--today,
.vuecal__cell--current {
  background-color: rgba(100, 200, 255, 0.1);
  border: 1px solid rgba(80, 141, 173, 0.8);
}
.vuecal:not(.vuecal--day-view) .vuecal__cell--selected {
  background-color: rgba(100, 200, 255, 0.1);
  border: 1px solid rgba(100, 200, 255, 0.8);
}
.vuecal__cell--selected:before {
  border-color: rgba(66, 185, 131, 0.5);
}

.vuecal__cell--highlighted:not(.vuecal__cell--has-splits),
.vuecal__cell-split--highlighted {
  background-color: rgba(195, 255, 225, 0.5);
}
.vuecal__arrow.vuecal__arrow--highlighted,
.vuecal__view-btn.vuecal__view-btn--highlighted {
  background-color: rgba(136, 236, 191, 0.25);
}
.vuecal__cell-split.schedule {
  background-color: rgba(221, 221, 221, 0.5);
}
.vuecal__cell-split.availability {
  background-color: rgba(149, 149, 149, 0.39);
}

.vuecal__event.event {
  background-color: #b3bce4;
  border: 1px solid #a3a3a3;
  color: #fff;
}
.vuecal__event.available {
  background-color: #87ad69;
  border: 1px solid rgb(141, 141, 141);
  color: #fff;
}
.vuecal__event.overridable {
  background-color: rgba(253, 156, 66, 0.9);
  border: 1px solid rgb(233, 136, 46);
  color: #fff;
}
.vuecal__event.unavailable {
  background-color: rgba(255, 102, 102, 0.9);
  border: 1px solid rgb(141, 141, 141);
  color: #fff;
}

.vuecal__no-event {
  display: none;
}

.vuecal__cell--before-min {
  color: grey;
}
.vuecal__cell--disabled {
  color: grey;
}
</style>
