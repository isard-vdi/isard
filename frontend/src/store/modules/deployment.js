import i18n from '@/i18n'
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { DeploymentsUtils } from '../../utils/deploymentsUtils'
import { DomainsUtils } from '../../utils/domainsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import router from '@/router'

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
    }
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
    }
  },
  mutations: {
    resetDeploymentState: (state) => {
      Object.assign(state, getDefaultState())
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
    }
  },
  actions: {
    resetDeploymentState (context) {
      context.commit('resetDeploymentState')
    },
    socket_deploymentUpdate (context, data) {
      const deployment = DeploymentsUtils.parseDeployment(JSON.parse(data))
      context.commit('update_deployment', deployment)
    },
    socket_deploymentdesktopAdd (context, data) {
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data))
      context.commit('add_deploymentdesktop', deploymentdesktop)
    },
    socket_deploymentdesktopUpdate (context, data) {
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data))
      context.commit('update_deploymentdesktop', deploymentdesktop)
    },
    socket_deploymentdesktopDelete (context, data) {
      const deploymentdesktop = DeploymentsUtils.parseDeploymentDesktop(JSON.parse(data))
      context.commit('remove_deploymentdesktop', deploymentdesktop)
    },
    fetchDeployment (context, data) {
      axios.get(`${apiV3Segment}/deployment/${data.id}`).then(response => {
        context.commit('setDeployment', DeploymentsUtils.parseDeployment(response.data))
      })
    },
    setSelectedDesktop (context, selectedDesktop) {
      context.commit('setSelectedDesktop', selectedDesktop)
    },
    toggleVisible (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t(payload.visible ? 'messages.info.making-invisible-deployment' : 'messages.info.making-visible-deployment'), '', true, 1000)
      axios.put(`${apiV3Segment}/deployments/visible/${payload.id}`, { stop_started_domains: payload.stopStartedDomains }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },

    deleteDeployment (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-deployment'), '', true, 1000)
      axios.delete(`${apiV3Segment}/deployments/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
        if (payload.path) {
          context.dispatch('navigate', payload.path)
        }
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    recreateDeployment (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.recreating-deployment'), '', true, 1000)
      axios.put(`${apiV3Segment}/deployments/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    downloadDirectViewerCSV (_, payload) {
      axios.get(`${apiV3Segment}/deployments/directviewer_csv/${payload.id}`, { params: { reset: payload.reset } }).then(response => {
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
      axios.put(`${apiV3Segment}/deployments/start/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    stopDeploymentDesktops (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.stopping-desktops'), '', true, 1000)
      axios.put(`${apiV3Segment}/deployments/stop/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    countGroupsUsers (_, groups) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.counting-desktops'), '', true, 1000)
      return axios.put(`${apiV3Segment}/groups_users/count`, groups).catch(e => {
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
    goToEditDeployment (context, editDeploymentId) {
      context.commit('setEditDeploymentId', editDeploymentId)
      router.replace({ name: 'deploymentEdit', params: { id: editDeploymentId } })
    },
    fetchDeploymentInfo (context, deploymentId) {
      axios.get(`${apiV3Segment}/deployment/info/${deploymentId}`).then(response => {
        context.commit('setDomain', DomainsUtils.parseDomain(response.data))
        context.commit('setDeployment', { name: response.data.tag_name })
        context.dispatch('setAllowedGroupsUsers', { groups: response.data.allowed.groups, users: response.data.allowed.users })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDeployment (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      axios.put(`${apiV3Segment}/deployment/${data.id}`, data).then(response => {
        context.dispatch('navigate', 'deployments')
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDeploymentUsers (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      axios.put(`${apiV3Segment}/deployment/users/${data.id}`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
