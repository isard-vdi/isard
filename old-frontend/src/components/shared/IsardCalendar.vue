<template>
  <vue-cal
    id="vuecal"
    style=""
    sticky-split-labels
    today-button
    :locale="$i18n.locale === 'eu' ? 'en' : $i18n.locale"
    :events="events"
    :disable-views="['years', 'year']"
    :split-days="splitDays"
    :time-from="timeFrom * 60"
    :time-to="timeTo * 60"
    :events-on-month-view="'short'"
    :snap-to-time="snapToTime"
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
    >
    <template #split-label="{ split }">
      <i
        v-if="split.id === 2"
        class="icon material-icons"
      >person</i>
      <i
        v-else
        class="icon material-icons"
      >event</i>
      <strong :style="`color: ${split.color}`">{{ split.label }}</strong>
    </template>
    <template #event="{ event }">
      <div
        v-b-tooltip.hover
        :title="event.title"
      >
        <div v-if="view.type === 'month'">
          <span>{{ event.start.formatTime("HH:mm") }} - {{ event.end.formatTime("HH:mm") }} {{ event.title }}</span>
        </div>
        <div v-else>
          <small>
            {{ event.start.formatTime("HH:mm") }} - {{ event.end.formatTime("HH:mm") }}
          </small>
          <h6>
            {{ event.title }}
          </h6>
          <small v-if="event.subtitle">{{ event.subtitle }} </small>
        </div>
      </div>
    </template>
  </vue-cal>
</template>
<script>
import VueCal from 'vue-cal'
// TODO: Import in locales
import 'vue-cal/dist/vuecal.css'
import 'vue-cal/dist/i18n/es.js'
import 'vue-cal/dist/i18n/ca.js'
import 'vue-cal/dist/i18n/de.js'
import 'vue-cal/dist/i18n/fr.js'
import 'vue-cal/dist/i18n/ru.js'

export default {
  components: { VueCal },
  props: {
    events: {
      type: Array,
      required: true
    },
    splitDays: {
      type: Array,
      required: false,
      default: () => { return [] }
    },
    disabledSplit: {
      type: Number,
      required: false
    },
    view: {
      type: Object,
      required: true
    },
    timeFrom: {
      type: Number,
      required: false,
      default: 0
    },
    timeTo: {
      type: Number,
      required: false,
      default: 24
    },
    snapToTime: {
      type: Number,
      required: false,
      default: 15
    }
  },
  setup (props, { emit }) {
    const onViewChange = (event) => {
      console.log('cal onViewChange')
      event.startDate = event.firstCellDate
      emit('viewChanged', event)
    }

    const onEventCreate = (event) => {
      if (props.disabledSplit && event.split === props.disabledSplit) {
        return false
      }

      emit('eventCreated', event)
      return event
    }

    const onCellClick = (event) => {
      console.log('cal onCellClick')
      emit('cellClicked', event)
    }

    const onCellDrag = (event) => {
      console.log('cal onCellDrag')
      emit('cellDragged', event)
    }

    const onEventClick = (event, e) => {
      console.log('cal onEventClick')
      emit('eventClicked', event)
    }

    const onEventDblClick = (event, e) => {
      console.log('cal onEventDblClick')
      emit('eventDblClicked', event)
    }

    const scrollToCurrentTime = () => {
      const calendar = document.querySelector('#vuecal .vuecal__bg')
      const hours = 9 - props.timeFrom
      calendar.scrollTo({ top: hours * 40, behavior: 'smooth' })
    }
    return { onViewChange, onEventCreate, onCellClick, onCellDrag, onEventClick, onEventDblClick, scrollToCurrentTime }
  }
}
</script>
<style>
.vuecal__menu, .vuecal__cell-events-count {background-color: #4fb2f3; border: 1px solid #5a5a5a;}
.vuecal__title-bar {background-color: #368ec8;}

.vuecal__cell--today, .vuecal__cell--current {background-color: rgba(100,200,255,0.1); border: 1px solid rgba(80, 141, 173, 0.8);}
.vuecal:not(.vuecal--day-view) .vuecal__cell--selected {background-color: rgba(100,200,255,0.1); border: 1px solid rgba(100,200,255,0.8);}
.vuecal__cell--selected:before {border-color: rgba(66, 185, 131, 0.5);}
/* Cells and buttons get highlighted when an event is dragged over it. */
.vuecal__cell--highlighted:not(.vuecal__cell--has-splits),
.vuecal__cell-split--highlighted {background-color: rgba(195, 255, 225, 0.5);}
.vuecal__arrow.vuecal__arrow--highlighted,
.vuecal__view-btn.vuecal__view-btn--highlighted {background-color: rgba(136, 236, 191, 0.25);}
.vuecal__cell-split.schedule {background-color: rgba(221, 221, 221, 0.5);}
.vuecal__cell-split.availability {background-color: rgba(149, 149, 149, 0.39);}

.event {
  background-color: #b3bce4;
  border: 1px solid #a3a3a3;
  color: #fff;
}

.available {
  background-color: #87AD69;
  border: 1px solid rgb(141, 141, 141);
  color: #fff;
}

.overridable {
  background-color: rgba(253, 156, 66, 0.9);
  border: 1px solid rgb(233, 136, 46);
  color: #fff;
}
.unavailable {
  background-color: rgba(255, 102, 102, 0.9);
  border: 1px solid rgb(141, 141, 141);
  color: #fff;
}

.vuecal__no-event {
  display: none
}

.vuecal__cell--before-min {color: 'grey'}
.vuecal__cell--disabled {color: 'grey'}
</style>
