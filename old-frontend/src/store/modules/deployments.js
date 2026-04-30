import i18n from '@/i18n'
import router from '@/router'
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { DeploymentsUtils } from '../../utils/deploymentsUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    deployments: [],
    deployments_loaded: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getDeployments: state => {
      return state.deployments
    },
    getDeploymentsLoaded: state => {
      return state.deployments_loaded
    }
  },
  mutations: {
    resetDeploymentsState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setDeployments: (state, deployments) => {
      state.deployments = deployments
      state.deployments_loaded = true
    },
    add_deployments: (state, deployment) => {
      // Idempotent — see add_desktop in modules/desktops.js for the
      // same race-against-cache pattern.
      const existingIndex = state.deployments.findIndex(d => d.id === deployment.id)
      if (existingIndex === -1) {
        state.deployments = [...state.deployments, deployment]
      } else {
        state.deployments = state.deployments.map(d => d.id === deployment.id ? { ...d, ...deployment } : d)
      }
    },
    update_deployments: (state, deployment) => {
      const item = state.deployments.find(d => d.id === deployment.id)
      if (item) {
        Object.assign(item, deployment)
      }
    },
    remove_deployments: (state, deployment) => {
      const deploymentIndex = state.deployments.findIndex(d => d.id === deployment.id)
      if (deploymentIndex !== -1) {
        state.deployments.splice(deploymentIndex, 1)
      }
    }
  },
  actions: {
    resetDeploymentsState (context) {
      context.commit('resetDeploymentsState')
    },
    socket_deploymentsAdd (context, data) {
      const deployment = DeploymentsUtils.parseDeploymentsItem(JSON.parse(data))
      context.commit('add_deployments', deployment)
    },
    socket_deploymentsUpdate (context, data) {
      // Partial-row merge — keep keys present in the payload so the
      // exclude_none=True change-handler emit doesn't overwrite
      // cached fields with undefined.
      const deployments = DeploymentsUtils.parseDeploymentsItem(JSON.parse(data), { partial: true })
      context.commit('update_deployments', deployments)
    },
    socket_deploymentsDelete (context, data) {
      const deployment = JSON.parse(data)
      context.commit('remove_deployments', deployment)
    },
    fetchDeployments (context) {
      axios.get(`${apiV3Segment}/items/deployments`).then(response => {
        context.commit('setDeployments', DeploymentsUtils.parseDeployments(response.data.deployments))
      })
    },
    createNewDeployment (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-deployment'), '', true, 1000)
      axios.post(`${apiV3Segment}/item/deployment`, payload).then(response => {
        // this._vm.$snotify.clear()
        router.push({ name: 'deployment_desktops', params: { id: response.data.id } })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
