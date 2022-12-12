import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { BookingUtils } from '../../utils/bookingUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import i18n from '@/i18n'
import { DateUtils } from '../../utils/dateUtils'

const getDefaultState = () => {
  return {
    booking: {
      priority: {
        forbidTime: 0,
        maxTime: 0,
        maxItems: 0
      },
      item: {
        id: '',
        name: ''
      },
      view: {
        timeframe: '', // month | week | day
        viewType: '', // item | resume
        itemType: '', // desktop | deployment
        start: '',
        end: ''
      },
      events: [],
      modalShow: false,
      eventModal: {
        id: '',
        title: '',
        startDate: '',
        startTime: '',
        endDate: '',
        endTime: '',
        type: ''
      }
    }
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getBookingItem: state => {
      return state.booking.item
    },
    getBookingView: state => {
      return state.booking.view
    },
    getBookingEvents: state => {
      return state.booking.events
    },
    getBookingPriority: state => {
      return state.booking.priority
    },
    getBookingModalShow: state => {
      return state.booking.modalShow
    },
    getBookingEventModal: state => {
      return state.booking.eventModal
    }
  },
  mutations: {
    resetSchedulerState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setBookingView: (state, view) => {
      state.booking.view = view
    },
    setBookingItemId: (state, itemId) => {
      state.booking.item.id = itemId
    },
    setBookingItemName: (state, itemName) => {
      state.booking.item.name = itemName
    },
    setBookingViewItemType: (state, itemType) => {
      state.booking.view.itemType = itemType
    },
    setBookingEvents: (state, events) => {
      state.booking.events = events
    },
    setBookingPriority: (state, priority) => {
      state.booking.priority = priority
    },
    setBookingModalShow: (state, modalShow) => {
      state.booking.modalShow = modalShow
    },
    setBookingEventModal: (state, eventModal) => {
      state.booking.eventModal = eventModal
    },
    add_booking: (state, booking) => {
      state.booking.events = [...state.booking.events, booking]
    },
    update_booking: (state, booking) => {
      const item = state.booking.events.find(b => b.id === booking.id)
      Object.assign(item, booking)
    },
    remove_booking: (state, booking) => {
      const bookingIndex = state.booking.events.findIndex(b => b.id === booking.id)
      if (bookingIndex !== -1) {
        state.booking.events.splice(bookingIndex, 1)
      }
    }
  },
  actions: {
    socket_bookingitemAdd (context, data) {
      const booking = BookingUtils.parseEvent(JSON.parse(data))
      context.commit('add_booking', booking)
    },
    socket_bookingitemUpdate (context, data) {
      const booking = BookingUtils.parseEvent(JSON.parse(data))
      context.commit('update_booking', booking)
    },
    socket_bookingitemDelete (context, data) {
      const booking = JSON.parse(data)
      context.commit('remove_booking', booking)
    },
    fetchEvents (context, data) {
      axios.get(`${apiV3Segment}/bookings/user/${data.itemId}/${data.itemType}`, { params: { startDate: data.startDate, endDate: data.endDate, returnType: data.returnType } }).then(response => {
        context.commit('setBookingEvents', BookingUtils.parseEvents(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchAllEvents (context, data) {
      axios.get(`${apiV3Segment}/bookings/user`, { params: { startDate: data.startDate, endDate: data.endDate } }).then(response => {
        context.commit('setBookingEvents', BookingUtils.parseEvents(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchPriority (context, data) {
      axios.get(`${apiV3Segment}/bookings/priority/${data.itemType}/${data.itemId}`).then(response => {
        context.commit('setBookingPriority', BookingUtils.parsePriority(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    goToItemBooking (context, item) {
      context.commit('setBookingItemId', item.id)
      context.commit('setBookingItemName', item.name)

      const start = DateUtils.localTimeToUtc(DateUtils.pastMonday().format('YYYY-MM-DD HH:mm'))
      const end = DateUtils.localTimeToUtc(DateUtils.nextSunday().format('YYYY-MM-DD HH:mm'))
      context.dispatch('setBookingCurrentCalendarView', { itemType: item.type, viewType: 'item', timeframe: 'week', start: start, end: end })

      // Retrieve events between currently viewing dates
      const eventsData = {
        itemId: item.id,
        itemType: item.type,
        startDate: start,
        endDate: end,
        returnType: 'all'
      }
      context.dispatch('fetchEvents', eventsData)
      context.dispatch('fetchPriority', { itemId: item.id, itemType: item.type })
      context.dispatch('navigate', 'booking')
    },
    setBookingCurrentCalendarView (context, view) {
      context.commit('setBookingView', view)
    },
    changeCurrentView (context, data) {
      context.dispatch('setBookingCurrentCalendarView', { itemType: data.itemType, viewType: data.viewType, timeframe: data.timeframe, start: data.start, end: data.end })
      const eventsData = {
        startDate: data.start,
        endDate: data.end
      }
      if (data.viewType === 'summary') {
        context.dispatch('fetchAllEvents', eventsData)
      } else {
        eventsData.returnType = data.viewType === 'month' ? 'events' : 'all'
        eventsData.itemId = context.getters.getBookingItem.id
        eventsData.itemType = context.getters.getBookingView.itemType
        context.dispatch('fetchEvents', eventsData)
      }
    },
    showBookingModal (context, show) {
      context.commit('setBookingModalShow', show)
    },
    eventModalData (context, data) {
      context.commit('setBookingEventModal', data)
    },
    resetModalData (context) {
      context.commit('setBookingEventModal', {
        id: '',
        type: '',
        startDate: '',
        startTime: '',
        endDate: '',
        endTime: ''
      })
    },
    createEvent (context, payload) {
      const events = context.getters.getBookingEvents
      const priority = context.getters.getBookingPriority
      const { priorityAllowed, error } = BookingUtils.priorityAllowed({
        date: DateUtils.stringToDate(payload.date),
        end: DateUtils.stringToDate(payload.end)
      }, priority)
      const canCreate = BookingUtils.canCreate(payload, events)

      if (priorityAllowed && canCreate) {
        const data = {
          element_id: payload.elementId,
          element_type: payload.elementType,
          title: payload.title,
          start: DateUtils.formatAsUTC(payload.date),
          end: DateUtils.formatAsUTC(payload.end)
        }
        axios.post(`${apiV3Segment}/booking/event`, data).then(response => {
          this._vm.$snotify.clear()
          context.dispatch('resetModalData')
          context.dispatch('showBookingModal', false)
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      } else if (!priorityAllowed) {
        context.dispatch('showNotification', { message: error })
      } else if (!canCreate) {
        context.dispatch('showNotification', { message: i18n.t('messages.info.no-availability-event') })
      } else {
        context.dispatch('showNotification', { message: 'messages.info.not-created-event' })
      }
    },
    editEvent (context, payload) {
      const events = context.getters.getBookingEvents
      const canCreate = BookingUtils.canCreate(payload, events)

      if (canCreate) {
        const formData = new FormData()
        formData.append('element_id', payload.elementId)
        formData.append('element_type', payload.elementType)
        formData.append('event_id', payload.id)
        formData.append('title', payload.title)
        formData.append('start', DateUtils.formatAsUTC(payload.date))
        formData.append('end', DateUtils.formatAsUTC(payload.end))
        axios.put(`${apiV3Segment}/booking/event/${payload.id}`, formData).then(response => {
          this._vm.$snotify.clear()
          context.dispatch('resetModalData')
          context.dispatch('showBookingModal', false)
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      } else {
        context.dispatch('showNotification', { message: i18n.t('messages.info.no-availability-event') })
      }
    },
    deleteEvent (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-event'), '', true, 1000)
      axios.delete(`${apiV3Segment}/booking/event/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
        context.dispatch('resetModalData')
        context.dispatch('showBookingModal', false)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    resetSchedulerState (context) {
      context.commit('resetSchedulerState')
    },
    fetchBookingsSummary (context) {
      const start = DateUtils.localTimeToUtc(DateUtils.pastMonday().format('YYYY-MM-DD HH:mm'))
      const end = DateUtils.localTimeToUtc(DateUtils.nextSunday().format('YYYY-MM-DD HH:mm'))
      context.dispatch('setBookingCurrentCalendarView', { type: 'week', viewType: 'summary', start: start, end: end })
      const eventsData = {
        startDate: start,
        endDate: end
      }
      context.dispatch('fetchAllEvents', eventsData)
    }
  }
}
