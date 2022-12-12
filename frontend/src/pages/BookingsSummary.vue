<template>
  <b-container
    id="content"
    class="calendar-container"
    fluid
  >
    <b-row>
      <b-col class="text-center">
        <h4>{{ $t("components.bookings.summary.title") }}</h4>
      </b-col>
    </b-row>
    <b-row>
      <b-col class="calendar-row-container">
        <IsardCalendar
          :disabled-split="1"
          :events="events"
          :view="view"
          :snap-to-time="15"
          @viewChanged="viewChange"
          @eventClicked="onCalendarEventClicked"
          @cellDragged="onCalendarCellDragged"
        />
      </b-col>
    </b-row>
    <EventModal />
  </b-container>
</template>
<script>
import EventModal from '@/components/booking/EventModal'
import { computed } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import IsardCalendar from '@/components/shared/IsardCalendar'

export default {
  components: { EventModal, IsardCalendar },
  setup (_, context) {
    const $store = context.root.$store
    const view = computed(() => $store.getters.getBookingView)
    const item = computed(() => $store.getters.getBookingItem)
    const events = computed(() => $store.getters.getBookingEvents || [])
    const priority = computed(() => $store.getters.getBookingPriority)
    const role = computed(() => $store.getters.getUser.role_id)

    $store.dispatch('fetchBookingsSummary')

    const refreshEvents = () => { // Force the refresh of the calendar in frontend with a fake event
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
      $store.dispatch('changeCurrentView', { itemType: 'all', viewType: view.value.viewType, timeframe: event.view, start: DateUtils.localTimeToUtc(event.startDate), end: DateUtils.localTimeToUtc(event.endDate) })
    }

    // Click on calendar event
    const onCalendarEventClicked = (event, e) => {
      $store.dispatch('showBookingModal', true)
      $store.dispatch('eventModalData', {
        type: 'view',
        id: event.id,
        title: event.title,
        startDate: DateUtils.formatAsDate(event.start),
        startTime: DateUtils.formatAsTime(event.start),
        endDate: DateUtils.formatAsDate(event.end),
        endTime: DateUtils.formatAsTime(event.end)
      })
    }

    const onCalendarCellDragged = (event, e) => {
      refreshEvents()
      return {}
    }

    return {
      item,
      role,
      priority,
      events,
      view,
      onCalendarEventClicked,
      viewChange,
      onCalendarCellDragged
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
