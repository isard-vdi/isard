<template>
  <b-container
    id="content"
    class="calendar-container"
    fluid
  >
    <b-row>
      <b-col>
        <b-button
          class="ms-2 me-2 mb-2"
          pill
          variant="outline-secondary"
          @click="hideSplit(0)"
        >
          <b-icon
            v-if="splitDays[0].hide"
            icon="circle"
            aria-hidden="true"
            class="text-medium-gray"
            font-scale="0.75"
            shift-v="3"
          />
          <b-icon
            v-else
            style="color: rgba(255, 102, 102, 0.9)"
            icon="circle-fill"
            aria-hidden="true"
            class="text-medium-gray"
            font-scale="0.75"
            shift-v="3"
          />
          {{ splitDays[0].label }}
        </b-button>
        <b-button
          pill
          variant="outline-secondary"
          class="ml-2 mr-2 mb-2"
          @click="hideSplit(1)"
        >
          <b-icon
            v-if="splitDays[1].hide"
            icon="circle"
            aria-hidden="true"
            class="text-medium-gray"
            font-scale="0.75"
            shift-v="3"
          />
          <b-icon
            v-else
            style="color: rgba(100,200,255,.8);"
            icon="circle-fill"
            aria-hidden="true"
            class="text-medium-gray"
            font-scale="0.75"
            shift-v="3"
          />
          {{ splitDays[1].label }}
        </b-button>
      </b-col>
      <b-col class="text-center">
        <h4>{{ item.name }}</h4>
      </b-col>
      <b-col />
    </b-row>
    <b-row>
      <b-col class="calendar-row-container">
        <IsardCalendar
          :disabled-split="1"
          :events="events"
          :split-days="splitDays"
          :view="view"
          :snap-to-time="15"
          @viewChanged="viewChange"
          @eventClicked="onCalendarEventClicked"
          @cellClicked="onCalendarCellClicked"
          @cellDragged="onCalendarCellDragged"
        />
      </b-col>
    </b-row>
    <EventModal />
  </b-container>
</template>
<script>

import i18n from '@/i18n'
import EventModal from '@/components/booking/EventModal'
import { computed, ref, onMounted, onUnmounted, watch } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import { BookingUtils } from '@/utils/bookingUtils'
import IsardCalendar from '@/components/shared/IsardCalendar'
import { bookingEventsSettings } from '@/utils/bookingEventsSettings'
import { get } from 'lodash'

export default {
  components: { EventModal, IsardCalendar },
  setup (_, context) {
    const $store = context.root.$store
    const view = computed(() => $store.getters.getBookingView)
    const item = computed(() => $store.getters.getBookingItem)
    const events = computed(() => $store.getters.getBookingEvents || [])
    const priority = computed(() => $store.getters.getBookingPriority)
    const role = computed(() => $store.getters.getUser.role_id)
    const modalShow = computed(() => $store.getters.getBookingModalShow)

    let eventEnd = ''
    let eventEndDate = ''
    let eventEndTime = ''

    const cellDoubleClickActive = computed(() => get(bookingEventsSettings.cellDoubleClickActive, `${role.value}.${view.value.timeframe}.${view.value.viewType}`))
    const cellDragActive = computed(() => get(bookingEventsSettings.cellDragActive, `${role.value}.${view.value.timeframe}.${view.value.viewType}`))
    const eventClickActive = computed(() => get(bookingEventsSettings.eventClickActive, `${role.value}.${view.value.timeframe}.${view.value.viewType}`))
    const showAvailabilitySplit = computed(() => get(bookingEventsSettings.showAvailabilitySplit, `${role.value}.${view.value.timeframe}.${view.value.viewType}`))

    onMounted(() => {
      if (view.value.viewType === '') {
        $store.dispatch('navigate', 'desktops')
      }
    })

    onUnmounted(() => {
      $store.dispatch('resetSchedulerState')
    })

    // Calendar Split
    const splitDays = ref([
      { id: 1, label: i18n.t('components.bookings.item.split-labels.availability'), hide: false, class: 'split-availability' },
      { id: 2, label: i18n.t('components.bookings.item.split-labels.bookings'), hide: false, class: 'split-schedule' }
    ])

    watch(showAvailabilitySplit, (showAvailabilitySplit, prevVal) => {
      splitDays.value[0].hide = !showAvailabilitySplit
    }, { immediate: true })

    // refresh calendar on modal close
    watch(modalShow, (modalShow, prevVal) => {
      if (!modalShow) {
        refreshEvents()
      }
    })

    const refreshEvents = () => { // Force the refresh of the calendar in frontend with a kake event
      const fakebooking = {
        id: 1,
        start: '2000-01-29 18:15',
        end: '2000-01-29 18:30',
        title: 'fakeevent',
        editable: false,
        split: 2,
        class: 'event'
      }
      $store.commit('add_booking', fakebooking)
      $store.commit('remove_booking', fakebooking)
    }

    // Retrieve events between currently vieweing dates when changing view interval
    const viewChange = (event) => {
      $store.dispatch('changeCurrentView', { itemType: view.value.itemType, viewType: view.value.viewType, timeframe: event.view, start: DateUtils.localTimeToUtc(event.startDate), end: DateUtils.localTimeToUtc(event.endDate) })
      if (view.value.timeframe === 'month') {
        hideSplit(0)
      }
    }

    // Hide split
    const hideSplit = (arrayPos) => {
      if (view.value.timeframe !== 'month') {
        splitDays.value[arrayPos].hide = !splitDays.value[arrayPos].hide
      }
    }

    const onEventCreate = (event) => {} // Don't use this event as it disables the drag creation of an event

    // Click on calendar cell
    const onCalendarCellClicked = (event) => {
      event.start = event.date
      event.end = eventEnd
      if (!cellDoubleClickActive.value === true) { return }
      if (DateUtils.dateToMoment(event.start).isBefore(new Date())) {
        event.start = new Date().addMinutes(5)
      }

      const canCreate = BookingUtils.canCreate(event, events.value)
      const { priorityAllowed, error } = BookingUtils.priorityAllowed(event, priority.value)
      if (event.split === 2 && priorityAllowed && canCreate) {
        $store.dispatch('showBookingModal', true)
        $store.dispatch('eventModalData', {
          type: 'create',
          startDate: DateUtils.formatAsDate(event.start),
          startTime: DateUtils.formatAsTime(event.start),
          endDate: eventEndDate,
          endTime: eventEndTime
        })

        eventEnd = ''
        eventEndDate = ''
        eventEndTime = ''
      } else if (event.split === 2) {
        if (!priorityAllowed) {
          $store.dispatch('showNotification', { message: error })
        } else if (!canCreate) {
          $store.dispatch('showNotification', { message: i18n.t('messages.info.no-availability-event') })
        } else {
          $store.dispatch('showNotification', { message: i18n.t('messages.info.not-created-event') })
        }
        eventEnd = ''
        eventEndDate = ''
        eventEndTime = ''
        refreshEvents() // To delete the temporary event from calendar after drag and drop process error
      }
    }

    // Drag inside calendar
    const onCalendarCellDragged = (event) => {
      if (!cellDragActive.value) {
        refreshEvents()
        return
      }

      eventEnd = event.end
      eventEndDate = DateUtils.formatAsDate(event.end)
      eventEndTime = DateUtils.formatAsTime(event.end)
    }

    // Click on calendar event
    const onCalendarEventClicked = (event, e) => {
      if (!eventClickActive.value) { return }

      let type = 'view'
      if (DateUtils.dateToMoment(new Date()).isBefore(event.end)) {
        type = 'edit'
      }
      $store.dispatch('showBookingModal', true)
      $store.dispatch('eventModalData', {
        type: type,
        id: event.id,
        title: event.title,
        startDate: DateUtils.formatAsDate(event.start),
        startTime: DateUtils.formatAsTime(event.start),
        endDate: DateUtils.formatAsDate(event.end),
        endTime: DateUtils.formatAsTime(event.end)
      })
    }

    return {
      item,
      role,
      priority,
      events,
      view,
      splitDays,
      onEventCreate,
      onCalendarEventClicked,
      hideSplit,
      viewChange,
      onCalendarCellClicked,
      onCalendarCellDragged,
      refreshEvents
    }
  }
}
</script>

<style>
.calendar-container {
  height: 100vh;
  width: 95%;
}

.calendar-row-container {
  height: calc(100vh - 15rem);
}

.vuecal__menu {
    background-color: transparent;
    border-bottom-color: #CED3D6;
    border-top-color: #CED3D6;
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
    background: #87AD69;
    color: #fff;
}

.vuecal__title-bar {
    background: #CED3D6;
}

.weekday-label {
  margin: 0.1rem
}

.split-availability {
  color: #ED9A9A;
}

.split-schedule {
  color: #C0C4DE
}

.vuecal__cell .split-availability {
  background-color: #f1d5d5;
  color: rgba(0,0,0,.25);
  cursor: not-allowed;
}

.vuecal__now-line {
  color: rgb(143, 12, 12)
}

.vuecal__cell--selected  {
  background-color: inherit !important;
}

.vuecal__cell--today {
   background-color: inherit !important;
}

.vuecal__time-cell {
  color: rgb(26, 25, 25) !important;
  margin-right: 0.2rem
}
</style>
