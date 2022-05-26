import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { AllowedUtils, tablesConfig } from '../../utils/allowedUtils'

const getDefaultState = () => {
  return {
    groups: [],
    selectedGroups: false,
    groupsChecked: false,
    users: [],
    selectedUsers: false,
    usersChecked: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getGroups: state => {
      return state.groups
    },
    getSelectedGroups: state => {
      return state.selectedGroups
    },
    getUsers: state => {
      return state.users
    },
    getSelectedUsers: state => {
      return state.selectedUsers
    }
  },
  mutations: {
    resetAllowedState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setGroups: (state, groups) => {
      state.groups = groups
    },
    setSelectedGroups: (state, selectedGroups) => {
      state.selectedGroups = selectedGroups
    },
    setUsers: (state, users) => {
      state.users = users
    },
    setSelectedUsers: (state, selectedUsers) => {
      state.selectedUsers = selectedUsers
    }
  },
  actions: {
    resetAllowedState (context) {
      context.commit('resetAllowedState')
    },
    fetchAllowedTerm (context, data) {
      axios.post(`${apiV3Segment}/admin/alloweds/term/${data.table}`, data).then(response => {
        context.commit(tablesConfig[data.table].mutations.set, AllowedUtils.parseAllowed(data.table, response.data))
      })
    },
    updateSelected (context, data) {
      context.commit(tablesConfig[data.table].mutations.setSelected, data.selected)
    }
  }
}
