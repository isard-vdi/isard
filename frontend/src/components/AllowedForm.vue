<template>
  <div>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <b-form-checkbox
          v-model="groupsChecked"
          :value="true"
          :unchecked-value="false"
        >
          {{ $t('forms.allowed.groups') }}
        </b-form-checkbox>
      </b-col>
    </b-row>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <AllowedSelect
          id="allowedGroupsField"
          :placeholder="placeholder"
          :disabled="!groupsChecked"
          :table="'groups'"
          :options="groups"
          :selected-values="selectedGroups"
        />
      </b-col>
    </b-row>
    <b-row class="mt-4">
      <b-col
        cols="12"
        xl="12"
      >
        <b-form-checkbox
          v-model="usersChecked"
          :value="true"
          :unchecked-value="false"
        >
          {{ $t('forms.allowed.users') }}
        </b-form-checkbox>
      </b-col>
    </b-row>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <AllowedSelect
          id="allowedUsersField"
          :placeholder="placeholder"
          :disabled="!usersChecked"
          :table="'users'"
          :options="users"
          :selected-values="selectedUsers"
        />
      </b-col>
    </b-row>
  </div>
</template>
<script>
import { computed, watch } from '@vue/composition-api'
import { mapGetters } from 'vuex'
import AllowedSelect from '@/components/AllowedSelect.vue'
import i18n from '@/i18n'

export default {
  components: {
    AllowedSelect
  },
  setup (props, context) {
    const $store = context.root.$store
    const placeholder = context.root.$route.name === 'deploymentsnew' ? i18n.t('forms.allowed.placeholder') : `${i18n.t('forms.allowed.placeholder')} ${i18n.t('forms.allowed.empty')}`

    // Groups
    const groupsChecked = computed({
      get: () => $store.getters.getGroupsChecked,
      set: (value) => $store.commit('setGroupsChecked', value)
    })
    const groups = computed(() => $store.getters.getGroups)
    const selectedGroups = computed(() => $store.getters.getSelectedGroups)
    // Reset the dropdown when unchecking
    watch(groupsChecked, (checked, prevVal) => {
      if (checked === false) {
        $store.dispatch('updateOptions', { table: 'groups', selected: [] })
        $store.dispatch('updateSelected', { table: 'groups', selected: [] })
      }
    }, { immediate: true })

    // Users
    const usersChecked = computed({
      get: () => $store.getters.getUsersChecked,
      set: (value) => $store.commit('setUsersChecked', value)
    })
    const users = computed(() => $store.getters.getUsers)
    const selectedUsers = computed(() => $store.getters.getSelectedUsers)
    // Reset the dropdown when unchecking
    watch(usersChecked, (checked, prevVal) => {
      if (checked === false) {
        $store.dispatch('updateOptions', { table: 'users', selected: [] })
        $store.dispatch('updateSelected', { table: 'users', selected: [] })
      }
    }, { immediate: true })

    return {
      groups,
      selectedGroups,
      groupsChecked,
      users,
      selectedUsers,
      usersChecked,
      placeholder
    }
  },
  computed: {
    ...mapGetters([
      'getGroups',
      'getUsers'
    ])
  }
}
</script>
