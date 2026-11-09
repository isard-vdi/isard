import axios from 'axios'
import i18n from '@/i18n'
import { apiV3Segment } from '../../shared/constants'
import {
  TASK_DONE,
  blocksStart,
  hasStorageProblems,
  pendingTaskIds,
  planStorageProblems,
  roundDuration,
  totalSeconds
} from '../../utils/storageProblemsUtils'

// The disk problems of a desktop that cannot start: the new frontend's
// useStorageRepair composable and storage-tasks store, as a Vuex module.

export const WAIT_POLL_MS = 5000
export const RETRY_COOLDOWN_MS = 5 * 60000

// shared by every page, so a start retried from one is not retried again from another
const lastRetry = new Map()
// desktops whose start this app asked for: a later Failed is checked for disk problems
const startedHere = new Set()
let poll = null
let failed = false

const getDefaultState = () => {
  return {
    storageProblemsModal: {
      show: false,
      desktopId: null,
      desktopName: '',
      plan: null,
      errorMessage: null
    },
    storageTasks: {},
    watchedTasks: [],
    queuedHere: {}
  }
}

const state = getDefaultState()

const problemKey = (item) => `${item.storageId}:${item.problem.fix}`

const toastOptions = {
  timeout: 4000,
  showProgressBar: false,
  closeOnClick: true,
  pauseOnHover: true,
  position: 'centerTop',
  // snotify cuts a body at 150 characters by default
  bodyMaxLength: 400
}

export function storageProblemsDuration (seconds) {
  if (seconds == null) return i18n.t('components.storage-problems.duration.unknown')
  const { value, unit } = roundDuration(seconds)
  return i18n.t(`components.storage-problems.duration.${unit}`, { value })
}

export function storageProblemsEstimate (estimate) {
  return i18n.t('components.storage-problems.estimate', {
    tier: i18n.t(`components.storage-problems.tier.${(estimate && estimate.tier) || 'standard'}`),
    ahead: (estimate && estimate.ahead) || 0,
    duration: storageProblemsDuration(totalSeconds(estimate))
  })
}

function stopPolling () {
  if (poll) clearInterval(poll)
  poll = null
}

function startPolling (context) {
  if (!poll) poll = setInterval(() => context.dispatch('refreshStorageProblems'), WAIT_POLL_MS)
}

function storageProblemsUrl (desktopId) {
  return `${apiV3Segment}/item/desktop/${desktopId}/storage-problems`
}

function apply (context, report) {
  const plan = planStorageProblems(report)
  context.commit('setStorageProblemsModal', { plan })
  context.commit('setWatchedTasks', [
    ...new Set([...pendingTaskIds(plan), ...Object.values(context.state.queuedHere)])
  ])
  if (context.state.watchedTasks.length) startPolling(context)
  else stopPolling()
  return plan
}

function taskStatus (context, id) {
  const task = context.state.storageTasks[id]
  return task ? task.status : undefined
}

export default {
  state,
  getters: {
    getStorageProblemsModal: state => {
      return state.storageProblemsModal
    },
    getStorageTasks: state => {
      return state.storageTasks
    },
    isStorageProblemQueued: state => item => {
      return problemKey(item) in state.queuedHere
    }
  },
  mutations: {
    resetStorageProblemsState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setStorageProblemsModal: (state, modal) => {
      state.storageProblemsModal = { ...state.storageProblemsModal, ...modal }
    },
    updateStorageTask: (state, task) => {
      state.storageTasks = { ...state.storageTasks, [task.id]: { ...state.storageTasks[task.id], ...task } }
    },
    setWatchedTasks: (state, ids) => {
      state.watchedTasks = ids
    },
    setQueuedHere: (state, queued) => {
      state.queuedHere = queued
    }
  },
  actions: {
    socket_task (context, data) {
      const task = JSON.parse(data)
      if (!task || !task.id) return
      context.commit('updateStorageTask', task)
      const watched = context.state.watchedTasks
      if (!watched.length) return
      const statuses = watched.map((id) => taskStatus(context, id))
      if (!statuses.every((s) => s && TASK_DONE.includes(s))) return
      if (statuses.some((s) => s !== 'finished')) {
        failed = true
        this._vm.$snotify.error(
          i18n.t('components.storage-problems.failed', { name: context.state.storageProblemsModal.desktopName }),
          toastOptions
        )
      }
      return context.dispatch('refreshStorageProblems')
    },
    // Handle the disk problems behind a failed start; false when there are none.
    async diagnoseStorageProblems (context, data) {
      stopPolling()
      const desktop = context.getters.getDesktop(data.desktopId)
      context.commit('setStorageProblemsModal', {
        desktopId: data.desktopId,
        desktopName: (desktop && desktop.name) || data.desktopId,
        errorMessage: null
      })
      context.commit('setQueuedHere', {})
      failed = false
      let found
      try {
        const response = await axios.put(storageProblemsUrl(data.desktopId))
        found = apply(context, response.data)
      } catch {
        return false
      }
      if (!hasStorageProblems(found)) return false
      // nothing left blocks a start that was just retried: the cause is elsewhere
      const retriedAt = lastRetry.get(data.desktopId) || 0
      if (!blocksStart(found) && !context.state.watchedTasks.length && Date.now() - retriedAt < RETRY_COOLDOWN_MS) {
        return false
      }
      context.commit('setStorageProblemsModal', { show: true })
      return true
    },
    async refreshStorageProblems (context) {
      const desktopId = context.state.storageProblemsModal.desktopId
      if (!desktopId) return
      let next
      try {
        const response = await axios.get(storageProblemsUrl(desktopId))
        next = apply(context, response.data)
      } catch {
        return
      }
      if (context.state.watchedTasks.some((id) => !TASK_DONE.includes(taskStatus(context, id) || ''))) return
      if (blocksStart(next) || failed) return
      stopPolling()
      context.commit('setStorageProblemsModal', { show: false })
      lastRetry.set(desktopId, Date.now())
      this._vm.$snotify.success(
        i18n.t('components.storage-problems.fixed', { name: context.state.storageProblemsModal.desktopName }),
        toastOptions
      )
      context.dispatch('changeDesktopStatus', { action: 'start', desktopId })
    },
    async fixDesktopStorage (context, item) {
      const modal = context.state.storageProblemsModal
      if (!modal.desktopId || !item.problem.fix) return
      context.commit('setStorageProblemsModal', { errorMessage: null })
      try {
        const response = await axios.put(
          `${apiV3Segment}/item/desktop/${modal.desktopId}/storage/${item.storageId}/fix/${item.problem.fix}`
        )
        const taskId = response.data.task_id
        context.commit('setQueuedHere', { ...context.state.queuedHere, [problemKey(item)]: taskId })
        context.commit('setWatchedTasks', [...new Set([...context.state.watchedTasks, taskId])])
        startPolling(context)
        // body only, as every other toast here: snotify draws a title in a large font
        const queued = i18n.t('components.storage-problems.fix-queued', {
          fix: i18n.t(`components.storage-problems.fix.${item.problem.fix}`),
          name: modal.desktopName
        })
        this._vm.$snotify.success(`${queued}. ${storageProblemsEstimate(response.data.estimate)}`, toastOptions)
      } catch (e) {
        const code = e.response && e.response.data && e.response.data.description_code
        context.commit('setStorageProblemsModal', {
          errorMessage: code && i18n.te(`errors.${code}`)
            ? i18n.t(`errors.${code}`)
            : i18n.t('components.storage-problems.fix-error')
        })
      }
    },
    closeStorageProblemsModal (context) {
      stopPolling()
      context.commit('setStorageProblemsModal', { show: false })
    },
    storageProblemsStarted (_, desktopId) {
      startedHere.add(desktopId)
    },
    storageProblemsDesktopStatus (context, data) {
      if (!startedHere.has(data.id)) return
      if (data.status === 'Started') {
        startedHere.delete(data.id)
      } else if (data.status === 'Failed') {
        startedHere.delete(data.id)
        context.dispatch('diagnoseStorageProblems', { desktopId: data.id })
      }
    }
  }
}
