import { DesktopUtils } from '../../utils/desktopsUtils'

export default {
  state: {
    deployments: [],
    deployments_loaded: false
  },
  getters: {
    getDeployments: state => {
      return state.deployments
    },
    getDeploymentsLoaded: state => {
      return state.deployments_loaded
    }
  },
  mutations: {
    setDeployments: (state, desktops) => {
      state.deployments = desktops
      state.deployments_loaded = true
    }
  },
  actions: {
    fetchDeployments (context) {
      return new Promise((resolve, reject) => {
        context.commit('setDeployments', DesktopUtils.parseDeployments([
          {
            id: 1,
            name: 'AAAA',
            startedDesktops: 2,
            totalDesktops: 10
          },
          {
            id: 2,
            name: 'BBBB',
            startedDesktops: 7,
            totalDesktops: 10
          },
          {
            id: 3,
            name: 'CCCC',
            startedDesktops: 3,
            totalDesktops: 10
          }
        ]))
        resolve()
      })
    }
  }
}
