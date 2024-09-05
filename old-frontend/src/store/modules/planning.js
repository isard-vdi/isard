import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { PlanningUtils } from '../../utils/planningUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { DateUtils } from '../../utils/dateUtils'
import i18n from '@/i18n'

const getDefaultState = () => {
  return {
    planning: {
      view: {
        timeframe: '', // month | week | day
        start: '',
        end: ''
      },
      events: [],
      reservable: {
        types: [],
        items: [],
        subitems: []
      },
      selected: {
        type: '',
        item: '',
        subitem: ''
      },
      modalShow: false,
      eventModal: {
        id: '',
        itemId: '',
        subitemId: null,
        type: '',
        startDate: '',
        startTime: '',
        endDate: '',
        endTime: ''
      }
    }
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getPlanningView: state => {
      return state.planning.view
    },
    getPlanningEvents: state => {
      return state.planning.events
    },
    getPlanningReservableTypes: state => {
      return state.planning.reservable.types
    },
    getPlanningReservableItems: state => {
      return state.planning.reservable.items
    },
    getPlanningReservableSubitems: state => {
      return state.planning.reservable.subitems
    },
    getPlanningSelectedReservableType: state => {
      return state.planning.selected.type
    },
    getPlanningSelectedReservableItem: state => {
      return state.planning.selected.item
    },
    getPlanningSelectedReservableSubitem: state => {
      return state.planning.selected.subitem
    },
    getPlanningModalShow: state => {
      return state.planning.modalShow
    },
    getPlanningEventModal: state => {
      return state.planning.eventModal
    }
  },
  mutations: {
    resetPlanningState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setPlanningView: (state, view) => {
      state.planning.view = view
    },
    setPlanningEvents: (state, events) => {
      state.planning.events = events
    },
    setPlanningReservableTypes: (state, reservableTypes) => {
      state.planning.reservable.types = reservableTypes
    },
    setPlanningReservableItems: (state, reservableItems) => {
      state.planning.reservable.items = reservableItems
    },
    setPlanningReservableSubitems: (state, reservableSubitems) => {
      state.planning.reservable.subitems = reservableSubitems
    },
    setPlanningSelectedReservableType: (state, selectedReservableType) => {
      state.planning.selected.type = selectedReservableType
    },
    setPlanningSelectedReservableItem: (state, selectedReservableItem) => {
      state.planning.selected.item = selectedReservableItem
    },
    setPlanningSelectedReservableSubitem: (state, selectedReservableSubitem) => {
      state.planning.selected.subitem = selectedReservableSubitem
    },
    setPlanningModalShow: (state, modalShow) => {
      state.planning.modalShow = modalShow
    },
    setPlanningEventModal: (state, eventModal) => {
      state.planning.eventModal = eventModal
    },
    add_plan: (state, plan) => {
      state.planning.events = [...state.planning.events, plan]
    },
    update_plan: (state, plan) => {
      const item = state.planning.events.find(p => p.id === plan.id)
      Object.assign(item, plan)
    },
    remove_plan: (state, plan) => {
      const planningIndex = state.planning.events.findIndex(p => p.id === plan.id)
      if (planningIndex !== -1) {
        state.planning.events.splice(planningIndex, 1)
      }
    }
  },
  actions: {
    socket_planAdd (context, data) {
      const plan = PlanningUtils.parseEvent(JSON.parse(data))
      context.commit('add_plan', plan)
    },
    socket_planUpdate (context, data) {
      const plan = PlanningUtils.parseEvent(JSON.parse(data))
      context.commit('update_plan', plan)
    },
    socket_planDelete (context, data) {
      const plan = PlanningUtils.parseEvent(JSON.parse(data))
      context.commit('remove_plan', plan)
    },
    fetchReservableTypes (context) {
      return axios.get(`${apiV3Segment}/admin/reservables`).then(response => {
        context.commit('setPlanningReservableTypes', response.data)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchReservableItems (context, data) {
      return axios.get(`${apiV3Segment}/admin/reservables/${data.itemType}`).then(response => {
        context.commit('setPlanningReservableItems', PlanningUtils.parseItems(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchReservableSubitems (context, data) {
      return axios.get(`${apiV3Segment}/admin/reservables/enabled/${data.itemType}/${data.itemId}`).then(response => {
        context.commit('setPlanningReservableSubitems', PlanningUtils.parseSubitems(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchPlanning (context, data) {
      return axios.get(`${apiV3Segment}/admin/reservables_planner/${data.itemId}/${data.start}/${data.end}`).then(response => {
        context.commit('setPlanningEvents', PlanningUtils.parseEvents(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    resetPlanningEvents (context) {
      context.commit('setPlanningEvents', [])
    },
    resetPlanningState (context) {
      context.commit('resetPlanningState')
    },
    setPlannerCurrentCalendarView (context, view) {
      context.commit('setPlanningView', view)
    },
    changePlanningCurrentView (context, data) {
      context.dispatch('setPlannerCurrentCalendarView', { timeframe: data.timeframe, start: data.start, end: data.end })

      // TODO: Fetch events if there's a profile selected
    },
    showPlanningModal (context, show) {
      context.commit('setPlanningModalShow', show)
    },
    eventPlanningModalData (context, data) {
      context.commit('setPlanningEventModal', data)
    },
    resetPlanningModalData (context) {
      context.commit('setPlanningEventModal', {
        itemId: '',
        subitemId: '',
        type: '',
        startDate: '',
        startTime: '',
        endDate: '',
        endTime: ''
      })
    },
    createPlanningEvent (context, payload) {
      const start = DateUtils.stringToDate(payload.start)
      const end = DateUtils.stringToDate(payload.end)
      if (start < new Date()) {
        context.dispatch('showNotification', { message: i18n.t('components.bookings.errors.past-booking') })
        return
      } else if (end <= start) {
        context.dispatch('showNotification', { message: i18n.t('components.bookings.errors.end-before-start') })
        return
      } else if (DateUtils.getMinutesBetweenDates(start, end) < 5) {
        context.dispatch('showNotification', { message: i18n.t('components.bookings.errors.minimum-time') })
        return
      }

      const data = {
        item_type: payload.type,
        item_id: payload.itemId,
        subitem_id: payload.subitemId,
        start: DateUtils.formatAsUTC(payload.start),
        end: DateUtils.formatAsUTC(payload.end)
      }

      axios.post(`${apiV3Segment}/admin/reservables_planner`, data).then(response => {
        this._vm.$snotify.clear()
        context.dispatch('resetPlanningModalData')
        context.dispatch('showPlanningModal', false)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editPlanningEvent (context, payload) {
      const data = {
        subitem_id: payload.subitemId,
        start: DateUtils.formatAsUTC(payload.start),
        end: DateUtils.formatAsUTC(payload.end)
      }

      axios.put(`${apiV3Segment}/admin/reservables_planner/${payload.id}`, data).then(response => {
        this._vm.$snotify.clear()
        context.dispatch('resetPlanningModalData')
        context.dispatch('showPlanningModal', false)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deletePlanningEvent (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-event'), '', true, 1000)
      axios.delete(`${apiV3Segment}/admin/reservables_planner/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
        context.dispatch('resetPlanningModalData')
        context.dispatch('showPlanningModal', false)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
