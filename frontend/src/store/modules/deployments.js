import { DesktopUtils } from '../../utils/desktopsUtils'
import { apiAxios } from '@/router/auth'
import router from '@/router'

export default {
  state: {
    deployments: [],
    deployments_loaded: false,
    deployment: [],
    deployment_loaded: false
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
    }
  },
  actions: {
    fetchDeployments (context) {
      return apiAxios.get('/deployments').then(response => {
        context.commit('setDeployments', DesktopUtils.parseDeployments(response.data))
      }).catch(err => {
        console.log(err)
        router.push({
          name: 'Error',
          params: { code: err.response && err.response.status.toString() }
        })
      })
    },
    fetchDeployment (context, data) {
      return apiAxios.get(`/deployment/${data.id}`).then(response => {
        context.commit('setDeployment', DesktopUtils.parseDeployment(response.data))
      }).catch(err => {
        console.log(err)
        router.push({
          name: 'Error',
          params: { code: err.response && err.response.status.toString() }
        })
      })
    }
  }
}
