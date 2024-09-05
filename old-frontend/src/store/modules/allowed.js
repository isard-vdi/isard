import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { AllowedUtils, tablesConfig } from '../../utils/allowedUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    id: '',
    groups: [], // Available groups
    selectedGroups: [],
    groupsChecked: false,
    users: [], // Available users
    selectedUsers: [],
    usersChecked: false,
    modalShow: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getId: state => {
      return state.id
    },
    getGroups: state => {
      return state.groups
    },
    getSelectedGroups: state => {
      return state.selectedGroups
    },
    getGroupsChecked: state => {
      return state.groupsChecked
    },
    getUsers: state => {
      return state.users
    },
    getSelectedUsers: state => {
      return state.selectedUsers
    },
    getUsersChecked: state => {
      return state.usersChecked
    },
    getShowAllowedModal: state => {
      return state.modalShow
    }
  },
  mutations: {
    resetAllowedState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setId: (state, id) => {
      state.id = id
    },
    setGroups: (state, groups) => {
      state.groups = groups
    },
    setSelectedGroups: (state, selectedGroups) => {
      state.selectedGroups = selectedGroups
    },
    setGroupsChecked: (state, groupsChecked) => {
      state.groupsChecked = groupsChecked
    },
    setUsers: (state, users) => {
      state.users = users
    },
    setSelectedUsers: (state, selectedUsers) => {
      state.selectedUsers = selectedUsers
    },
    setUsersChecked: (state, usersChecked) => {
      state.usersChecked = usersChecked
    },
    setShowAllowedModal: (state, modalShow) => {
      state.modalShow = modalShow
    }
  },
  actions: {
    resetAllowedState (context) {
      context.commit('resetAllowedState')
    },
    fetchAllowedTerm (context, data) {
      return axios.post(`${apiV3Segment}/admin/allowed/term/${data.table}`, data).then(response => {
        if (data.table === 'media') {
          context.commit(tablesConfig[data.kind].mutations.set, AllowedUtils.parseAllowed(data.kind, response.data))
        } else {
          context.commit(tablesConfig[data.table].mutations.set, AllowedUtils.parseAllowed(data.table, response.data))
        }
      })
    },
    fetchAllowed (context, data) {
      return axios.post(`${apiV3Segment}/allowed/table/${data.table}`, data).then(response => {
        context.commit('setId', data.id)
        context.dispatch('setAllowedGroupsUsers', { groups: response.data.groups, users: response.data.users })
        context.dispatch('showAllowedModal', true)
      })
    },
    setAllowedGroupsUsers (context, data) {
      // Groups
      if (data.groups !== false) {
        context.dispatch('updateChecked', { table: 'groups', checked: true })
      }
      context.commit('setGroups', AllowedUtils.parseAllowed('groups', data.groups))
      context.commit('setSelectedGroups', AllowedUtils.parseAllowed('groups', data.groups))
      // Users
      if (data.users !== false) {
        context.dispatch('updateChecked', { table: 'users', checked: true })
      }
      context.commit('setUsers', AllowedUtils.parseAllowed('users', data.users))
      context.commit('setSelectedUsers', AllowedUtils.parseAllowed('users', data.users))
    },
    updateAllowed (context, data) {
      axios.post(`${apiV3Segment}/admin/allowed/update/${data.table}`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateChecked (context, data) {
      context.commit(tablesConfig[data.table].mutations.setChecked, data.checked)
    },
    updateSelected (context, data) {
      context.commit(tablesConfig[data.table].mutations.setSelected, data.selected)
    },
    updateOptions (context, data) {
      context.commit(tablesConfig[data.table].mutations.set, data.selected)
    },
    showAllowedModal (context, show) {
      context.commit('setShowAllowedModal', show)
    }
  }
}
