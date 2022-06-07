import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { DeploymentsUtils } from '../../utils/deploymentsUtils'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import i18n from '@/i18n'
import router from '@/router'

export default {
  state: {
    deployments: [],
    deployments_loaded: false,
    deployment: {
      desktops: []
    },
    deployment_loaded: false,
    selectedDesktop: {},
    deploymentsShowStarted: false
  },
  getters: {
    getDeployments: state => {
      return state.deployments
    },
    getDeploymentsLoaded: state => {
      return state.deployments_loaded
    },
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
    }
  },
  mutations: {
    setDeployments: (state, deployments) => {
      state.deployments = deployments
      state.deployments_loaded = true
    },
    setDeployment: (state, deployment) => {
      state.deployment = deployment
      state.deployment_loaded = true
    },
    setSelectedDesktop: (state, selectedDesktop) => {
      state.selectedDesktop = selectedDesktop
    },
    add_deployment: (state, deployment) => {
      state.deployments = [...state.deployments, deployment]
    },
    update_deployment: (state, deployment) => {
      const item = state.deployments.find(d => d.id === deployment.id)
      if (item) {
        Object.assign(item, deployment)
      }
    },
    remove_deployment: (state, deployment) => {
      const deploymentIndex = state.deployments.findIndex(d => d.id === deployment.id)
      if (deploymentIndex !== -1) {
        state.deployments.splice(deploymentIndex, 1)
      }
    },
    add_deploymentdesktop: (state, deploymentdesktop) => {
      state.deployment.desktops = [...state.deployment.desktops, deploymentdesktop]
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
    }
  },
  actions: {
    socket_deploymentAdd (context, data) {
      const deployment = DeploymentsUtils.parseDeploymentsItem(JSON.parse(data))
      context.commit('add_deployment', deployment)
    },
    socket_deploymentUpdate (context, data) {
      const deployment = DeploymentsUtils.parseDeploymentsItem(JSON.parse(data))
      context.commit('update_deployment', deployment)
    },
    socket_deploymentDelete (context, data) {
      const deployment = JSON.parse(data)
      context.commit('remove_deployment', deployment)
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
      const deploymentdesktop = JSON.parse(data)
      context.commit('remove_deploymentdesktop', deploymentdesktop)
    },
    fetchDeployments (context) {
      axios.get(`${apiV3Segment}/deployments`).then(response => {
        context.commit('setDeployments', DeploymentsUtils.parseDeployments(response.data))
      })
    },
    fetchDeployment (context, data) {
      axios.get(`${apiV3Segment}/deployment/${data.id}`).then(response => {
        context.commit('setDeployment', DeploymentsUtils.parseDeployment(response.data))
        context.commit('setDesktops', DesktopUtils.parseDesktops(response.data.desktops))
      })
    },
    setSelectedDesktop (context, selectedDesktop) {
      context.commit('setSelectedDesktop', selectedDesktop)
    },
    toggleDeploymentsShowStarted (context) {
      context.commit('toggleDeploymentsShowStarted')
    },
    createNewDeployment (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-deployment'), '', true, 1000)
      axios.post(`${apiV3Segment}/deployments`, payload).then(response => {
        // this._vm.$snotify.clear()
        router.push({ name: 'deployment_desktops', params: { id: response.data.id } })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    toggleVisible (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-deployment'), '', true, 1000)
      axios.put(`${apiV3Segment}/deployments/visible/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteDeployment (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-deployment'), '', true, 1000)
      axios.delete(`${apiV3Segment}/deployments/${payload.id}`).then(response => {
        this._vm.$snotify.clear()
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
      axios.get(`${apiV3Segment}/deployments/directviewer_csv/${payload.id}`).then(response => {
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
    }
  }
}
