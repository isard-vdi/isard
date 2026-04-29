import i18n from '@/i18n'
import router from '@/router'
import axios from 'axios'
import * as cookies from 'tiny-cookie'
import { apiV3Segment, sessionCookieName } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    viewers: localStorage.viewers ? JSON.parse(localStorage.viewers) : {},
    desktops: [],
    currentTab: 'desktops',
    desktops_loaded: false,
    viewType: 'grid',
    showStarted: false,
    filters: {
      desktops: ''
    },
    directLink: {
      modalShow: false,
      link: '',
      domainId: '',
      enabled: null
    },
    resetModal: {
      show: false,
      item: {
        id: '',
        action: ''
      }
    },
    desktopModal: {
      show: false,
      type: '',
      item: {
        id: ''
      }
    },
    bastionTargets: [],
    bastionModal: {
      show: false,
      desktop: {},
      bastion: { http: {}, ssh: {} }
    },
    pendingOperations: {}, // Track pending desktop operations for button state management
    // Ids of desktops the WS just removed. setDesktops filters incoming
    // REST rows against this so a fetchDesktops response in flight at
    // delete time can't re-add the doomed desktop. 5-second TTL drops
    // entries on read so a re-spawn with the same id (rare on temporal)
    // isn't permanently masked.
    recentlyDeletedIds: {}
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getDesktops: state => {
      return state.desktops
    },
    getDesktop: state => (id) => {
      return state.desktops.find(d => d.id === id)
    },
    getDesktopsLoaded: state => {
      return state.desktops_loaded
    },
    getViewers: state => {
      return state.viewers
    },
    getViewType: state => {
      return state.viewType
    },
    getShowStarted: state => {
      return state.showStarted
    },
    getDesktopsFilter: state => {
      return state.filters.desktops
    },
    getCurrentTab: state => {
      return state.currentTab
    },
    getDirectLinkModalShow: state => {
      return state.directLink.modalShow
    },
    getDirectLink: state => {
      return state.directLink.link
    },
    getDirectLinkDomainId: state => {
      return state.directLink.domainId
    },
    getDirectLinkEnabled: state => {
      return state.directLink.enabled
    },
    getResetModal: state => {
      return state.resetModal
    },
    getDesktopModal: state => {
      return state.desktopModal
    },
    getBastionTargets: state => {
      return state.bastionTargets
    },
    getBastionModal: state => {
      return state.bastionModal
    },
    isPendingOperation: (state) => (desktopId) => {
      const pending = state.pendingOperations[desktopId]
      if (!pending) return false

      // Auto-expire after 5 seconds (safety timeout)
      if (Date.now() - pending.timestamp > 5000) {
        return false
      }
      return true
    }
  },
  mutations: {
    resetDesktopsState: (state) => {
      Object.assign(state, getDefaultState())
    },
    resetDirectLinkState: (state) => {
      state.directLink.modalShow = false
      state.directLink.link = ''
      state.directLink.domainId = false
      state.directLink.enabled = null
    },
    setDesktops: (state, desktops) => {
      // Drop entries from recentlyDeletedIds older than 5s on every read,
      // and use the remaining set to filter REST rows for desktops the WS
      // already deleted (e.g. nonpersistent stopped → engine deletes →
      // socket_desktopDelete fires; a fetchDesktops in flight would
      // otherwise re-add the doomed row as a ghost card until the next
      // refresh).
      const now = Date.now()
      const TTL = 5000
      const stillRecent = {}
      for (const [id, ts] of Object.entries(state.recentlyDeletedIds)) {
        if (now - ts < TTL) stillRecent[id] = ts
      }
      state.recentlyDeletedIds = stillRecent
      const filtered = desktops.filter(d => !(d.id in stillRecent))

      // Race guard: a WS desktop_update can land between fetchDesktops
      // dispatch and the REST response. If the REST snapshot still shows a
      // transient state ("updating", "starting", "stopping", ...) but the
      // in-memory copy has already advanced to a terminal state via WS
      // ("started", "stopped", "failed"), keep the in-memory state — the
      // REST snapshot is older than what the user already saw on screen.
      const transient = ['updating', 'starting', 'stopping', 'shutting-down', 'creating', 'downloading', 'maintenance', 'working']
      const terminal = ['started', 'stopped', 'failed', 'waitingip']
      const prevById = new Map(state.desktops.map(d => [d.id, d]))
      state.desktops = filtered.map(d => {
        const prev = prevById.get(d.id)
        if (!prev || !prev.state || !d.state) return d
        const newS = String(d.state).toLowerCase()
        const prevS = String(prev.state).toLowerCase()
        if (transient.includes(newS) && terminal.includes(prevS)) return prev
        return d
      })
      state.desktops_loaded = true
    },
    updateViewers: (state, viewers) => {
      state.viewers = { ...state.viewers, ...viewers }
      localStorage.viewers = JSON.stringify(state.viewers)
    },
    setViewType: (state, type) => {
      state.viewType = type
    },
    toggleShowStarted: (state, type) => {
      state.showStarted = !state.showStarted
    },
    add_desktop: (state, desktop) => {
      // Idempotent: a desktop_add event can arrive while the same
      // desktop is still in the cache (e.g. visibility toggles or a
      // race against the initial fetch). Replace in place if it's
      // already there to avoid showing duplicate rows.
      const existingIndex = state.desktops.findIndex(d => d.id === desktop.id)
      if (existingIndex === -1) {
        state.desktops = [...state.desktops, desktop]
      } else {
        state.desktops = state.desktops.map(d => d.id === desktop.id ? { ...d, ...desktop } : d)
      }
    },
    update_desktop: (state, desktop) => {
      const item = state.desktops.find(d => d.id === desktop.id)
      if (item) {
        Object.assign(item, desktop)
      }
    },
    SET_PENDING_OPERATION: (state, { desktopId, action }) => {
      state.pendingOperations = {
        ...state.pendingOperations,
        [desktopId]: {
          action,
          timestamp: Date.now()
        }
      }
    },
    CLEAR_PENDING_OPERATION: (state, desktopId) => {
      const { [desktopId]: removed, ...rest } = state.pendingOperations
      state.pendingOperations = rest
    },
    remove_desktop: (state, desktop) => {
      // Stamp the id so a concurrently-fetching setDesktops won't re-add it.
      // setDesktops drops entries older than 5s on every read.
      state.recentlyDeletedIds = {
        ...state.recentlyDeletedIds,
        [desktop.id]: Date.now()
      }
      const desktopIndex = state.desktops.findIndex(d => d.id === desktop.id)
      if (desktopIndex !== -1) {
        state.desktops.splice(desktopIndex, 1)
      }
    },
    saveDesktopFilter: (state, payload) => {
      state.filters.desktops = payload.filter
    },
    setCurrentTab: (state, currentTab) => {
      state.currentTab = currentTab
    },
    setDirectLinkModalShow: (state, directLinkModalShow) => {
      state.directLink.modalShow = directLinkModalShow
    },
    setDirectLink: (state, directLink) => {
      state.directLink.link = directLink
    },
    setDirectLinkDomainId: (state, domainId) => {
      state.directLink.domainId = domainId
    },
    setDirectLinkEnabled: (state, enabled) => {
      state.directLink.enabled = enabled
    },
    setResetModal: (state, resetModal) => {
      state.resetModal = resetModal
    },
    setDesktopModal: (state, desktopModal) => {
      state.desktopModal = desktopModal
    },
    setBastionTargets: (state, bastionTargets) => {
      state.bastionTargets = bastionTargets
    },
    addBastionTarget: (state, target) => {
      state.bastionTargets = [...state.bastionTargets, target]
    },
    updateBastionTarget: (state, target) => {
      const item = state.bastionTargets.find(d => d.id === target.id)
      if (item) {
        Object.assign(item, target)
      }
    },
    removeBastionTarget: (state, target) => {
      const targetIndex = state.bastionTargets.findIndex(d => d.id === target.id)
      if (targetIndex !== -1) {
        state.bastionTargets.splice(targetIndex, 1)
      }
    },
    setBastionModal: (state, data) => {
      state.bastionModal.show = data.show
      const bastion = data.bastion || { http: {}, ssh: {} }
      state.bastionModal.bastion = bastion
      const desktop = data.desktop || {}
      state.bastionModal.desktop = desktop
    }
  },
  actions: {
    resetDesktopsState (context) {
      context.commit('resetDesktopsState')
    },
    resetDirectLinkState (context) {
      context.commit('resetDirectLinkState')
    },
    socket_desktopAdd (context, data) {
      const desktop = DesktopUtils.parseDesktop(JSON.parse(data))
      context.commit('add_desktop', desktop)
    },
    socket_desktopUpdate (context, data) {
      const desktop = DesktopUtils.parseDesktop(JSON.parse(data))

      // Only update if there are actual changes
      const existingDesktop = context.getters.getDesktop(desktop.id)
      if (existingDesktop) {
        const hasChanges = Object.keys(desktop).some(key =>
          JSON.stringify(existingDesktop[key]) !== JSON.stringify(desktop[key])
        )

        if (hasChanges) {
          context.commit('update_desktop', desktop)
          // Clear pending operation when status update arrives
          // This provides faster feedback than setTimeout
          if (['Started', 'Stopped', 'Failed', 'Verifying'].includes(desktop.status)) {
            context.commit('CLEAR_PENDING_OPERATION', desktop.id)
          }
        }
      } else {
        // Desktop doesn't exist, add it
        context.commit('add_desktop', desktop)
      }
    },
    socket_desktopDelete (context, data) {
      const desktop = JSON.parse(data)
      context.commit('remove_desktop', desktop)
    },
    socket_desktopsQueue (context, data) {
      data = JSON.parse(data)

      for (const [desktopId, queueInfo] of Object.entries(data)) {
        const desktop = context.getters.getDesktop(desktopId)
        if (desktop) {
          desktop.queue = queueInfo.position
          context.commit('update_desktop', desktop)
        }
      }
    },
    loadViewers (context, viewers) {
      context.commit('updateViewers', viewers)
    },
    fetchDesktops (context) {
      axios.get(`${apiV3Segment}/item/user/desktops`).then(response => {
        context.commit('setDesktops', DesktopUtils.parseDesktops(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createDesktop (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'))

      // ``data`` is a FormData built by TableList.vue / Card.vue with a
      // single ``template`` field. The v4 endpoint expects JSON, so we
      // extract the template id and send a minimal ``{template_id}`` body.
      const templateId = data instanceof FormData ? data.get('template') : data.template
      axios.post(
        `${apiV3Segment}/item/desktop/new-nonpersistent`,
        { template_id: templateId },
        { timeout: 25000 }
      ).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    changeDesktopStatus (context, data) {
      const isFromDeployment = data.deployment || false
      if (isFromDeployment) {
        delete data.deployment
      }
      // Check for pending operation (500ms debounce)
      const pending = context.state.pendingOperations[data.desktopId]
      if (pending && Date.now() - pending.timestamp < 500) {
        console.log('Debounced: Ignoring rapid click for desktop', data.desktopId)
        return Promise.resolve() // Return resolved promise for consistency
      }

      // Set pending state
      context.commit('SET_PENDING_OPERATION', {
        desktopId: data.desktopId,
        action: data.action
      })

      return axios.put(`${apiV3Segment}/item/desktop/${data.desktopId}/${data.action}`).then(response => {
        // apiv4's PUT /item/desktop/{id}/<action> returns SimpleResponse(id=...)
        // with no `status` field — only commit the optimistic state when the
        // legacy apiv3 shape leaks through (e.g. on a v3 fallback). Otherwise
        // wait for the change-handler WebSocket event to push the real state.
        if (response.data && response.data.status) {
          context.commit('update_desktop', { id: data.desktopId, state: DesktopUtils.parseState({ state: response.data.status }) })
        }
        // Once the request is successful, we can clear the pending state
        context.commit('CLEAR_PENDING_OPERATION', data.desktopId)
        if (data.action === 'start' && !isFromDeployment) {
          context.dispatch('fetchNotifications', { trigger: 'start_desktop', display: 'modal' })
        }
        return response
      }).catch(e => {
        // Clear immediately on error so user can retry
        context.commit('CLEAR_PENDING_OPERATION', data.desktopId)
        ErrorUtils.handleErrors(e, this._vm.$snotify)
        throw e
      })
    },
    cancelOperation (_, data) {
      this._vm.$snotify.prompt(`${i18n.t('messages.confirmation.cancel-operation')}`, {
        position: 'centerTop',
        buttons: [
          {
            text: `${i18n.t('messages.yes')}`,
            action: () => {
              this._vm.$snotify.clear()
              data.storage.forEach((storage) => {
                axios.put(`${apiV3Segment}/item/storage/${storage}/abort-operations`).then(() => {
                  ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.cancelling-operation'))
                }).catch(e => {
                  ErrorUtils.handleErrors(e, this._vm.$snotify)
                })
              })
            },
            bold: true
          },
          { text: `${i18n.t('messages.no')}` }
        ],
        placeholder: ''
      })
    },
    openDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.opening-desktop'))

      // Save last viewer selected
      const viewers = {}
      if (data.template) {
        viewers[data.template] = data.viewer
      } else {
        viewers[data.desktopId] = data.viewer
      }
      context.commit('updateViewers', viewers)

      axios.get(`${apiV3Segment}/item/desktop/${data.desktopId}/get-viewer/${data.viewer}`).then(response => {
        this._vm.$snotify.clear()

        const el = document.createElement('a')
        if (response.data.kind === 'file') {
          el.setAttribute(
            'href',
              `data:${response.data.mime};charset=utf-8,${encodeURIComponent(response.data.content)}`
          )
          el.setAttribute('download', `${response.data.name}.${response.data.ext}`)
          ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.file-downloaded'), '', false, 1000)
        } else if (response.data.kind === 'browser') {
          if (response.data.protocol === 'rdp') {
            cookies.setCookie('viewerToken', cookies.getCookie(sessionCookieName))
          }
          cookies.setCookie('browser_viewer', response.data.cookie)
          el.setAttribute('href', response.data.viewer)
          el.setAttribute('target', '_blank')
        }
        el.style.display = 'none'
        document.body.appendChild(el)
        el.click()
        document.body.removeChild(el)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createNewDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'), '', true, 1000)

      axios.post(`${apiV3Segment}/item/desktop`, data).then(response => {
        context.dispatch('updateBastion', response.data.id)
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createNewDesktopFromMedia (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'), '', true, 1000)

      axios.post(`${apiV3Segment}/item/desktop/from-media`, data).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-desktop'))
      const url = data.permanent
        ? `${apiV3Segment}/item/desktop/${data.id}?permanent=true`
        : `${apiV3Segment}/item/desktop/${data.id}`

      axios.delete(url).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    toggleDesktopVisible (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t(data.visible ? 'messages.info.making-invisible-desktop' : 'messages.info.making-visible-desktop'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/desktop/${data.id}/toggle-deployment-visibility`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteNonpersistentDesktop (_, desktopId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-desktop'))

      axios.delete(`${apiV3Segment}/item/desktop/${desktopId}?permanent=true`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateDesktopsFilter (context, payload) {
      context.commit('saveDesktopFilter', payload)
    },
    setViewType (context, viewType) {
      context.commit('setViewType', viewType)
    },
    toggleShowStarted (context) {
      context.commit('toggleShowStarted')
    },
    navigate (context, path) {
      router.push({ name: path })
    },
    updateCurrentTab (context, currentTab) {
      if (currentTab === 'sharedTemplates' && !context.getters.getSharedTemplatesLoaded) {
        context.dispatch('fetchAllowedTemplates', 'shared')
      }
      context.commit('setCurrentTab', currentTab)
    },
    fetchDirectLink (context, domainId) {
      axios.get(`${apiV3Segment}/item/desktop/${domainId}/get-share-link`).then(response => {
        context.commit('setDirectLinkDomainId', domainId)
        context.commit('setDirectLinkEnabled', !!response.data.link)
        context.commit('setDirectLink', response.data.link ? `${location.protocol}//${location.host}/vw/${response.data.link}` : '')
        context.dispatch('directLinkModalShow', true)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    directLinkModalShow (context, show) {
      context.commit('setDirectLinkModalShow', show)
    },
    toggleDirectLink (context, data) {
      axios.put(`${apiV3Segment}/item/desktop/${data.domainId}/update-share-link`, { enabled: !data.disabled }).then(response => {
        context.commit('setDirectLink', response.data.link ? `${location.protocol}//${location.host}/vw/${response.data.link}` : '')
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDesktopReservables (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      return axios.put(`${apiV3Segment}/item/desktop/${data.id}/edit`, { reservables: data.reservables }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateResetModal (context, data) {
      context.commit('setResetModal', data)
    },
    resetResetModal (context) {
      context.commit('setResetModal', {
        show: false,
        item: {
          id: '',
          action: ''
        }
      })
    },
    updateDesktopModal (context, data) {
      context.commit('setDesktopModal', data)
    },
    resetDesktopModal (context) {
      context.commit('setDesktopModal', {
        show: false,
        type: '',
        item: {
          id: ''
        }
      })
    },
    recreateDesktop (context, data) {
      axios.put(`${apiV3Segment}/item/desktop/${data.id}/recreate`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchBastionTargets (context) {
      const config = context.getters.getConfig
      if (config.canUseBastion === true) {
        axios.get(`${apiV3Segment}/items/bastions`).then(response => {
          context.commit('setBastionTargets', response.data)
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }
    },
    bastionModalShow (context, data) {
      context.commit('setBastionModal', data)
    },
    updateBastionAuthorizedKeys (context, data) {
      axios.put(`${apiV3Segment}/item/desktop/${data.desktop_id}/update-bastion-authorized-keys`, { authorized_keys: data.ssh.authorized_keys }).then(response => {
        ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.authorized-ssh-keys-updated'))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateBastionDomainName (context, data) {
      axios.put(`${apiV3Segment}/item/desktop/${data.desktop_id}/update-bastion-domain`, { domain_name: data.domain || null }).then(response => {
        ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.bastion-domain-updated'))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateBastionDomains (context, data) {
      axios.put(`${apiV3Segment}/item/desktop/${data.desktop_id}/update-bastion-domains`, { domains: data.domains || [] }).then(response => {
        ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.bastion-domains-updated'))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    verifyBastionDomain (context, data) {
      return axios.post(`${apiV3Segment}/item/desktop/${data.desktop_id}/verify-bastion-domain`, { domain: data.domain })
        .then(response => {
          return { success: true }
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
          return { success: false, error: e }
        })
    },
    socket_targetsAdd (context, data) {
      context.commit('addBastionTarget', JSON.parse(data))
    },
    socket_targetsUpdate (context, data) {
      context.commit('updateBastionTarget', JSON.parse(data))
    },
    socket_targetsDelete (context, data) {
      context.commit('removeBastionTarget', JSON.parse(data))
    },
    extendDesktopTimeout (context, desktopId) {
      return axios.put(`${apiV3Segment}/item/desktop/${desktopId}/extend-timeout`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
