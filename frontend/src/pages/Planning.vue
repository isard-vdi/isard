<template>
  <b-container
    id="content"
    class="calendar-container"
    fluid
  >
    <b-row class="mb-3">
      <b-col>
        <b-form-select
          v-model="selectedReservableType"
          :options="types"
        />
      </b-col>
      <b-col>
        <b-form-select
          v-model="selectedReservableItem"
          :options="items"
        />
      </b-col>
    </b-row>
    <b-row>
      <b-col class="calendar-row-container">
        <IsardCalendar
          :events="events"
          :view="view"
          :snap-to-time="15"
          @viewChanged="viewChange"
          @eventClicked="onCalendarEventClicked"
          @cellClicked="onCalendarCellClicked"
          @cellDragged="onCalendarCellDragged"
        />
      </b-col>
    </b-row>
    <PlanningModal />
  </b-container>
</template>
<script>
import PlanningModal from '@/components/booking/PlanningModal'
import { computed, ref, onMounted, watch, onUnmounted } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import IsardCalendar from '@/components/shared/IsardCalendar'
import { planningEventsSettings } from '@/utils/planningEventsSettings'
import { StringUtils } from '@/utils/stringUtils'
import { get } from 'lodash'

export default {
  components: { PlanningModal, IsardCalendar },
  setup (_, context) {
    const $store = context.root.$store
    const view = computed(() => $store.getters.getPlanningView)
    const role = computed(() => $store.getters.getUser.role_id)
    const modalShow = computed(() => $store.getters.getPlanningModalShow)
    const events = computed(() => $store.getters.getPlanningEvents || [])
    const reservableTypes = computed(() => $store.getters.getPlanningReservableTypes || [])
    const types = ref([])
    const reservableItems = computed(() => $store.getters.getPlanningReservableItems || [])
    const items = ref([])

    let eventEnd = ''
    let eventEndDate = ''
    let eventEndTime = ''

    const cellDoubleClickActive = computed(() => get(planningEventsSettings.cellDoubleClickActive, `${role.value}.${view.value.timeframe}`))
    const cellDragActive = computed(() => get(planningEventsSettings.cellDragActive, `${role.value}.${view.value.timeframe}`))
    const eventClickActive = computed(() => get(planningEventsSettings.eventClickActive, `${role.value}.${view.value.timeframe}`))

    const selectedReservableType = computed({
      get: () => $store.getters.getPlanningSelectedReservableType,
      set: (value) => $store.commit('setPlanningSelectedReservableType', value)
    })
    watch(selectedReservableType, (selectedReservableType, prevVal) => {
      if (!StringUtils.isNullOrUndefinedOrEmpty(selectedReservableType)) {
        $store.dispatch('fetchReservableItems', { itemType: selectedReservableType }).then(() => {
          items.value = reservableItems.value.map(item => {
            return {
              value: item.id,
              text: item.name
            }
          })
          $store.dispatch('resetPlanningEvents')
        })
      }
    }, { immediate: true })

    const selectedReservableItem = computed({
      get: () => $store.getters.getPlanningSelectedReservableItem,
      set: (value) => $store.commit('setPlanningSelectedReservableItem', value)
    })
    watch(selectedReservableItem, (selectedReservableItem, prevVal) => {
      if (!StringUtils.isNullOrUndefinedOrEmpty(selectedReservableItem)) {
        $store.dispatch('fetchPlanning', { itemId: selectedReservableItem, start: view.value.start, end: view.value.end })
      }
    }, { immediate: true })

    const refreshEvents = () => { // Force the refresh of the calendar in frontend with a fake event
      const fakeplanning = {
        id: 1,
        start: '2000-01-29 18:15',
        end: '2000-01-29 18:30',
        title: 'fakeevent',
        editable: false,
        split: 2,
        class: 'event'
      }
      $store.commit('add_plan', fakeplanning)
      $store.commit('remove_plan', fakeplanning)
    }

    // refresh calendar on modal close
    watch(modalShow, (modalShow, prevVal) => {
      if (!modalShow) {
        refreshEvents()
      }
    })

    onMounted(() => {
      const start = DateUtils.localTimeToUtc(DateUtils.pastMonday().format('YYYY-MM-DD HH:mm'))
      const end = DateUtils.localTimeToUtc(DateUtils.nextSunday().format('YYYY-MM-DD HH:mm'))
      $store.dispatch('setPlannerCurrentCalendarView', { timeframe: 'week', start: start, end: end })

      $store.dispatch('fetchReservableTypes').then(() => {
        types.value = reservableTypes.value.map(item => {
          return {
            value: item,
            text: item
          }
        })
      })
    })

    onUnmounted(() => {
      $store.dispatch('resetPlanningState')
    })

    // Retrieve events between currently vieweing dates when changing view interval
    const viewChange = (event) => {
      $store.dispatch('changePlanningCurrentView', { timeframe: event.view, start: DateUtils.localTimeToUtc(event.startDate), end: DateUtils.localTimeToUtc(event.endDate) })
      if (!StringUtils.isNullOrUndefinedOrEmpty(selectedReservableItem.value)) {
        $store.dispatch('fetchPlanning', { itemId: selectedReservableItem.value, start: DateUtils.localTimeToUtc(event.startDate), end: DateUtils.localTimeToUtc(event.endDate) })
      }
    }

    const onEventCreate = (event) => {} // Don't use this event as it disables the drag creation of an event

    // Click on calendar cell
    const onCalendarCellClicked = (event) => {
      event.end = eventEnd
      if (!cellDoubleClickActive.value === true) { return }

      if (DateUtils.dateToMoment(event).isBefore(new Date())) {
        event = new Date().addMinutes(5)
      }

      if (selectedReservableItem.value) {
        $store.dispatch('showPlanningModal', true)
        $store.dispatch('eventPlanningModalData', {
          type: 'create',
          subitemId: null,
          startDate: DateUtils.formatAsDate(event),
          startTime: DateUtils.formatAsTime(event),
          endDate: eventEndDate,
          endTime: eventEndTime
        })

        eventEnd = ''
        eventEndDate = ''
        eventEndTime = ''
      } else {
        eventEnd = ''
        eventEndDate = ''
        eventEndTime = ''
        refreshEvents()
      }
    }

    // Drag inside calendar
    const onCalendarCellDragged = (event) => {
      if (!cellDragActive.value) { return }

      eventEnd = event.end
      eventEndDate = DateUtils.formatAsDate(event.end)
      eventEndTime = DateUtils.formatAsTime(event.end)
    }

    // Click on calendar event
    const onCalendarEventClicked = (event, e) => {
      if (!eventClickActive.value) { return }

      const type = 'edit'
      // if (DateUtils.dateToMoment(new Date()).isBefore(event.start)) {
      //   type = 'edit' // Endpoint pending
      // }
      $store.dispatch('showPlanningModal', true)
      $store.dispatch('eventPlanningModalData', {
        type: type,
        id: event.id,
        itemId: selectedReservableItem.value,
        subitemId: event.subitemId,
        startDate: DateUtils.formatAsDate(event.start),
        startTime: DateUtils.formatAsTime(event.start),
        endDate: DateUtils.formatAsDate(event.end),
        endTime: DateUtils.formatAsTime(event.end)
      })
    }

    const onCalendarDragCreate = (event, e) => {
      console.log('drag create on calendar event')
    }

    const onCalendarEventDoubleClicked = (event, e) => {
      console.log('doubleclick on calendar event')
    }

    return {
      types,
      items,
      selectedReservableType,
      selectedReservableItem,
      events,
      view,
      onEventCreate,
      onCalendarEventClicked,
      viewChange,
      onCalendarCellClicked,
      onCalendarCellDragged,
      onCalendarEventDoubleClicked,
      onCalendarDragCreate
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
