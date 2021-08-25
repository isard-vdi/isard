import axios from 'axios'
import router from '@/router'
import { apiV3Segment } from '../../shared/constants'
import { DeploymentsUtils } from '../../utils/deploymentsUtils'

export default {
  state: {
    deployments: [],
    deployments_loaded: false,
    deployment: {
      desktops: []
    },
    deployment_loaded: false,
    selectedDesktop: {}
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
      Object.assign(item, deployment)
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
      Object.assign(item, deploymentdesktop)
    },
    remove_deploymentdesktop: (state, deploymentdesktop) => {
      const deploymentIndex = state.deployment.desktops.findIndex(d => d.id === deploymentdesktop.id)
      if (deploymentIndex !== -1) {
        state.deployment.desktops.splice(deploymentIndex, 1)
      }
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
      }).catch(err => {
        console.log(err)
        router.push({
          name: 'Error',
          params: { code: err.response && err.response.status.toString() }
        })
      })
    },
    fetchDeployment (context, data) {
      axios.get(`${apiV3Segment}/deployment/${data.id}`).then(response => {
        context.commit('setDeployment', DeploymentsUtils.parseDeployment(response.data))
      }).catch(err => {
        console.log(err)
        router.push({
          name: 'Error',
          params: { code: err.response && err.response.status.toString() }
        })
      })
    },
    setSelectedDesktop (context, selectedDesktop) {
      context.commit('setSelectedDesktop', selectedDesktop)
    }
  }
}
