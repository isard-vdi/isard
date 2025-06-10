import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'

const getDefaultState = () => {
  return {
    notifications: [],
    showNotificationModal: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getNotifications: (state) => {
      return state.notifications
    },
    getShowNotificationModal: (state) => {
      return state.showNotificationModal
    }
  },
  mutations: {
    addNotification (state, notification) {
      state.notifications.push(notification)
    },
    removeNotification (state, id) {
      state.notifications = state.notifications.filter(notification => notification.id !== id)
    },
    clearNotifications (state) {
      state.notifications = []
    },
    setShowNotificationModal (state, show) {
      state.showNotificationModal = show
    }
  },
  actions: {
    addNotification ({ commit }, notification) {
      const id = Date.now()
      commit('addNotification', { ...notification, id })
      setTimeout(() => {
        commit('removeNotification', id)
      }, 5000)
    },
    removeNotification ({ commit }, id) {
      commit('removeNotification', id)
    },
    clearNotifications ({ commit }) {
      commit('clearNotifications')
    },
    closeNotificationModal ({ commit }) {
      commit('setShowNotificationModal', false)
      commit('clearNotifications')
    },
    fetchNotifications ({ commit }, data) {
      axios.get(`${apiV3Segment}/notification/user/${data.trigger}/${data.display}`, data).then(response => {
        Object.values(response.data.notifications).forEach(notificationGroup => {
          Object.values(notificationGroup).forEach(notificationType => {
            notificationType.notifications.forEach(notification => {
              const formattedNotification = {
                id: notification.id || Date.now(),
                title: notification.title || notificationType.template?.title || '',
                body: notification.body || notificationType.template?.body || '',
                footer: notification.footer || notificationType.template?.footer || ''
              }
              commit('addNotification', formattedNotification)
            })
          })
        })
        if (state.notifications.length > 0) {
          commit('setShowNotificationModal', true)
        }
      }).catch(error => {
        console.error('Error fetching notifications:', error)
      })
    }
  }
}
