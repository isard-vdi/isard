import { DesktopUtils } from '../../utils/desktopsUtils'

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
    },
    fetchDeployment (context) {
      return new Promise((resolve, reject) => {
        context.commit('setDeployment', DesktopUtils.parseDeployment([
          {
            id: 1,
            user: 'melina',
            name: 'Deployment 1',
            description: 'Descripció de prova',
            state: '',
            viewers: [
              {
                type: 'browser',
                host: 'localhost',
                port: '443',
                token: '',
                vmHost: 'isard-hypervisor',
                vmPort: ''
              }
            ]
          },
          {
            id: 2,
            user: 'vitto',
            name: 'Deployment 2',
            description: 'Descripció de prova 2',
            state: '',
            viewers: [{
              type: 'browser',
              host: 'localhost',
              port: '443',
              token: '',
              vmHost: 'isard-hypervisor',
              vmPort: ''
            }]
          }
        ]))
      })
    }
  }
}
