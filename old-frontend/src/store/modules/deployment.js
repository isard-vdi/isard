import i18n from '@/i18n'
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { DeploymentsUtils } from '../../utils/deploymentsUtils'
import { DomainsUtils } from '../../utils/domainsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import router from '@/router'
import { AllowedUtils } from '../../utils/allowedUtils'

const getDefaultState = () => {
  return {
    deployment: {
      desktops: []
    },
    deployment_loaded: false,
    selectedDesktop: {},
    deploymentsShowStarted: false,
    deploymentModal: {
      show: false,
      type: 'visible',
      color: 'blue',
      item: {
        id: '',
        name: '',
        visible: false,
        stopStartedDomains: false,
        reset: false
      }
    },
    coOwners: {
      owner: {},
      coOwners: []
    },
    permissions: [],
    recreateButtonDisabled: false,
    showDeploymentLoadingModal: false,
    // Deployment ids currently in the engine's bulk-spawn loop. Bracketed by the
    // ``creating_desktops`` / ``end_creating_desktops`` WS events from
    // ``DesktopsProcessed.new_from_templateTh.process_desktops``. The detail
    // page reads this to keep the loading modal open across the whole spawn
    // pipeline — purely deriving from per-desktop states flickers between
    // batches because every loaded desktop momentarily reaches a terminal
    // state before the next ``deploymentdesktop_add`` arrives.
    bulkCreatingDeployments: []
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getDeployment: state => {
      return state.deployment
    },
    getDeploymentLoaded: state => {
      return state.deployment_loaded
    },
    getSelectedDesktop: state => {
      return state.selectedDesktop
    },
    getDeploymentsShowStarted: state => {
      return state.deploymentsShowStarted
    },
    getDeploymentModal: state => {
      return state.deploymentModal
    },
    getCoOwners: state => {
      return state.coOwners
    },
    getPermissions: state => {
      return state.permissions
    },
    isRecreateButtonDisabled: state => {
      return state.recreateButtonDisabled
    },
    getShowDeploymentLoadingModal: state => {
      return state.showDeploymentLoadingModal
    },
    isDeploymentBulkCreating: state => id => state.bulkCreatingDeployments.includes(id)
  },
  mutations: {
    resetDeploymentState: (state) => {
      // Preserve ``bulkCreatingDeployments`` across page navigation. It
      // tracks engine bulk-spawn operations that are scoped to the
      // session, not to whatever deployment row the user is currently
      // viewing — clearing it on every ``destroyed`` hook would lose the
      // open/close gate if the user briefly navigates away mid-spawn.
      const preserved = state.bulkCreatingDeployments
      Object.assign(state, getDefaultState())
      state.bulkCreatingDeployments = preserved
    },
    setDeployment: (state, deployment) => {
      state.deployment = deployment
      state.deployment_loaded = true
    },
    setSelectedDesktop: (state, selectedDesktop) => {
      state.selectedDesktop = selectedDesktop
    },
    update_deployment: (state, deployment) => {
      const item = state.deployment
      deployment.desktops = item.desktops // Don't update its desktops
      Object.assign(item, deployment)
    },
    add_deploymentdesktop: (state, deploymentdesktop) => {
      const item = state.deployment.desktops.find(d => d.id === deploymentdesktop.id)
      if (!item) {
        state.deployment.desktops = [...state.deployment.desktops, deploymentdesktop]
      }
    },
    update_deploymentdesktop: (state, deploymentdesktop) => {
      const item = state.deployment.desktops.find(d => d.id === deploymentdesktop.id)
      if (item) {
        Object.assign(item, deploymentdesktop)
      }
    },
    remove_deploymentdesktop: (state, deploymentdesktop) => {
      const deploymentIndex = state.deployment.desktops.findIndex(d => d.id === deploymentdesktop.id)
      if (deploymentIndex !== -1) {
        state.deployment.desktops.splice(deploymentIndex, 1)
      }
    },
    toggleDeploymentsShowStarted: (state, type) => {
      state.deploymentsShowStarted = !state.deploymentsShowStarted
    },
    setDeploymentModal: (state, deploymentModal) => {
      state.deploymentModal = deploymentModal
    },
    setCoOwners: (state, show) => {
      state.coOwners = show
    },
    setPermissions: (state, permissions) => {
      state.permissions = permissions
    },
    addPermission: (state, permission) => {
      state.permissions.push(permission)
    },
    removePermission: (state, permission) => {
      state.permissions = state.permissions.filter(p => p.id !== permission.id)
    },
    setDisableRecreateButton (state, value) {
      state.recreateButtonDisabled = value
    },
    setShowDeploymentLoadingModal (state, value) {
      state.showDeploymentLoadingModal = value
    },
    addBulkCreatingDeployment (state, id) {
      if (!state.bulkCreatingDeployments.includes(id)) {
        state.bulkCreatingDeployments = [...state.bulkCreatingDeployments, id]
      }
    },
    removeBulkCreatingDeployment (state, id) {
      state.bulkCreatingDeployments = state.bulkCreatingDeployments.filter(d => d !== id)
    }
  },
  actions: {
    resetDeploymentState (context) {
      context.commit('resetDeploymentState')
    },
    socket_deploymentUpdate (context, data) {
      // Partial-row merge — keep keys present in the payload so the
      // exclude_none=True change-handler emit doesn't overwrite
      // cached fields with undefined.
      const deployment = DeploymentsUtils.parseDeployment(JSON.parse(data), { partial: true })
      context.commit('update_deployment', deployment)
    },
    socket_deploymentdesktopAdd (context, data) {
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data))
      if (deploymentdesktop.tag === context.state.deployment.id) {
        context.commit('add_deploymentdesktop', deploymentdesktop)
      }
    },
    socket_deploymentdesktopUpdate (context, data) {
      // Partial-row merge — keep keys present in the payload so the
      // exclude_none=True change-handler emit doesn't overwrite
      // cached fields with undefined.
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data), { partial: true })
      if (deploymentdesktop.tag === context.state.deployment.id) {
        context.commit('update_deploymentdesktop', deploymentdesktop)
      }
    },
    socket_deploymentdesktopDelete (context, data) {
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data))
      if (deploymentdesktop.tag === context.state.deployment.id) {
        context.commit('remove_deploymentdesktop', deploymentdesktop)
      }
    },
    socket_creatingDesktops (context, data) {
      const payload = JSON.parse(data)
      // Track this regardless of route so the modal gate is correct even
      // when the event arrives BEFORE the detail page has mounted (engine
      // fires ``creating_desktops`` as soon as the POST returns).
      context.commit('addBulkCreatingDeployment', payload.deployment_id)
      if (router.currentRoute.name === 'deployment_desktops' && router.currentRoute.params.id === payload.deployment_id) {
        context.commit('setDisableRecreateButton', true)
      }
    },
    socket_endCreatingDesktops (context, data) {
      const payload = JSON.parse(data)
      context.commit('removeBulkCreatingDeployment', payload.deployment_id)
      if (router.currentRoute.name === 'deployment_desktops' && router.currentRoute.params.id === payload.deployment_id) {
        context.commit('setDisableRecreateButton', false)
        // Re-fetch the deployment so the desktop list, total counts, and
        // top-bar badges reconcile to the final state. Without this
        // re-fetch the page only shows the desktops that arrived via
        // ``deploymentdesktop_add`` AFTER ``fetchDeployment`` resolved —
        // and on apiv4-integration the engine's asyncio fan-out is fast
        // enough that most ``deploymentdesktop_add`` events fire BEFORE
        // ``fetchDeployment`` sets ``state.deployment.id``, so the
        // listener filter ``tag === state.deployment.id`` drops them.
        // The result was the user seeing 3 of 32 desktops with no error.
        context.dispatch('fetchDeployment', { id: payload.deployment_id })
      }
    },
    fetchDeployment (context, data) {
      // The Vue 2 detail page (Deployment.vue) renders a flat list of desktops
      // tagged in the deployment. apiv4's /item/deployment/{id} returns
      // {info, users} where each user only carries desktops_statuses counts,
      // so it's not enough on its own. The /videowall endpoint returns the
      // legacy flat {…, desktops:[…]} shape parseDeployment was written for,
      // and apiv4 also enriches it with total_users/total_desktops/desktops_each_user
      // so the recreate confirmation count is populated.
      axios.get(`${apiV3Segment}/item/deployment/${data.id}/videowall`).then(response => {
        context.commit('setDeployment', DeploymentsUtils.parseDeployment(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchDeploymentVideowall (context, data) {
      axios.get(`${apiV3Segment}/item/deployment/${data.id}/videowall`).then(response => {
        context.commit('setDeployment', DeploymentsUtils.parseDeployment(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    setSelectedDesktop (context, selectedDesktop) {
      context.commit('setSelectedDesktop', selectedDesktop)
    },
    toggleVisible (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t(payload.visible ? 'messages.info.making-invisible-deployment' : 'messages.info.making-visible-deployment'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/deployment/${payload.id}/toggle-visibility`, { stop_started_domains: payload.stopStartedDomains }).then(() => {
        // The change-handler `deployments_update` event will eventually push
        // the new value, but apply it locally now so the StatusBar icon and
        // the in-flight modal show the new state immediately.
        if (context.state.deployment && context.state.deployment.id === payload.id) {
          context.commit('update_deployment', { visible: !payload.visible })
        }
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },

    deleteDeployment (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-deployment'), '', true, 1000)
      const url = payload.permanent
        ? `${apiV3Segment}/item/deployment/${payload.id}?permanent=true`
        : `${apiV3Segment}/item/deployment/${payload.id}`
      axios.delete(url).then(response => {
        context.commit('remove_deployments', { id: payload.id })
        this._vm.$snotify.clear()
        if (payload.pathName) {
          context.dispatch('navigate', payload.pathName)
        }
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    recreateDeployment (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.recreating-deployment'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/deployment/${payload.id}/recreate`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    downloadDirectViewerCSV (_, payload) {
      axios.get(`${apiV3Segment}/item/deployment/${payload.id}/download-csv`, { params: { reset: payload.reset } }).then(response => {
        this._vm.$snotify.clear()
        const el = document.createElement('a')
        el.setAttribute(
          'href',
            `data: text/csv;charset=utf-8,${encodeURIComponent(response.data)}`
        )
        el.setAttribute('download', `${payload.id}_direct_viewer.csv`)
        el.style.display = 'none'
        document.body.appendChild(el)
        el.click()
        document.body.removeChild(el)
        ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.file-downloaded'), '', false, 1000)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    startDeploymentDesktops (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.starting-desktops'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/deployment/${payload.id}/start`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    stopDeploymentDesktops (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.stopping-desktops'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/deployment/${payload.id}/stop`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    countGroupsUsers (_, groups) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.counting-desktops'), '', true, 1000)
      return axios.put(`${apiV3Segment}/items/groups-users/count`, groups).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    checkDeploymentsCreateQuota (context, data) {
      return axios.post(`${apiV3Segment}/item/deployment/check-quota`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    toggleDeploymentsShowStarted (context) {
      context.commit('toggleDeploymentsShowStarted')
    },
    updateDeploymentModal (context, data) {
      context.commit('setDeploymentModal', data)
    },
    resetDeploymentModal (context) {
      context.commit('setDeploymentModal', {
        show: false,
        type: 'visible',
        item: {
          id: '',
          visible: false,
          stopStartedDomains: false,
          reset: false
        }
      })
    },
    goToEditDeployment (_context, editDeploymentId) {
      router.replace({ name: 'deploymentEdit', params: { id: editDeploymentId } })
    },
    fetchDeploymentInfo (context, deploymentId) {
      axios.get(`${apiV3Segment}/item/deployment/${deploymentId}/info`).then(response => {
        context.commit('setDomain', DomainsUtils.parseDomain(response.data))
        // /info returns the recipe under `name` and the deployment name
        // under `tag_name`. The form's "Deployment name" input must bind
        // to the deployment row, not the recipe.
        const deploymentName = response.data.tag_name || response.data.name
        context.commit('setDeployment', { name: deploymentName })
        context.dispatch('setAllowedGroupsUsers', { groups: response.data.allowed.groups, users: response.data.allowed.users })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDeployment (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      axios.put(`${apiV3Segment}/item/deployment/${data.id}/edit`, data).then(response => {
        context.dispatch('navigate', 'deployments')
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDeploymentUsers (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      axios.put(`${apiV3Segment}/item/deployment/${data.id}/edit-users`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchCoOwners (context, deploymentId) {
      return axios.get(`${apiV3Segment}/item/deployment/${deploymentId}/co-owners`).then(response => {
        const owner = AllowedUtils.parseUser(response.data.owner)
        const coOwners = AllowedUtils.parseAllowed('users', response.data.co_owners)
        context.commit('setCoOwners', { owner: owner, coOwners: coOwners })
        context.commit('setSelectedUsers', coOwners)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateCoOwners (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      axios.put(`${apiV3Segment}/item/deployment/${data.id}/co-owners`, { co_owners: data.users }).then(response => {
        context.dispatch('fetchCoOwners', data.id)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchPermissions (context, deploymentId) {
      axios.get(`${apiV3Segment}/item/deployment/${deploymentId}/permissions`).then(response => {
        context.commit('setPermissions', response.data)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    showDeploymentLoadingModal (context, value) {
      context.commit('setShowDeploymentLoadingModal', value)
    }
  }
}
