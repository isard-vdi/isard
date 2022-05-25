<template>
  <div>
    <b-row class="mt-4">
      <b-col cols="12" xl="12">
        <b-form-checkbox
          v-model="groupsChecked"
          :value="true"
          :unchecked-value="false"
        >
        {{$t('forms.allowed.groups')}}
        </b-form-checkbox>
      </b-col>
    </b-row>
    <b-row>
      <b-col cols="12" xl="12">
        <AllowedSelect id="allowedGroupsField" :placeholder="$t('forms.allowed.placeholder')" :reset="resetGroups" :disabled="!groupsChecked" :table="'groups'" :options="groups" />
      </b-col>
    </b-row>
    <b-row class="mt-4">
      <b-col cols="12" xl="12">
        <b-form-checkbox
          v-model="usersChecked"
          :value="true"
          :unchecked-value="false"
        >
        {{$t('forms.allowed.users')}}
        </b-form-checkbox>
      </b-col>
    </b-row>
    <b-row>
      <b-col cols="12" xl="12">
        <AllowedSelect id="allowedUsersField" :placeholder="$t('forms.allowed.placeholder')" :reset="resetUsers" :disabled="!usersChecked" :table="'users'" :options="users" />
      </b-col>
    </b-row>
  </div>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'
import { mapGetters } from 'vuex'
import AllowedSelect from '@/components/AllowedSelect.vue'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const groupsChecked = ref(false)
    const groups = computed(() => $store.getters.getGroups || [])
    let resetGroups = ref(false)
    watch(groupsChecked, (groupsChecked, prevVal) => {
      if (groupsChecked) {
        $store.dispatch('updateSelected', { table: 'groups', selected: [] })
      } else {
        $store.dispatch('updateSelected', { table: 'groups', selected: false })
      }
      resetGroups = true
    }, { immediate: true })

    const usersChecked = ref(false)
    const users = computed(() => $store.getters.getUsers || [])
    let resetUsers = ref(false)
    watch(usersChecked, (usersChecked, prevVal) => {
      if (usersChecked) {
        $store.dispatch('updateSelected', { table: 'users', selected: [] })
      } else {
        $store.dispatch('updateSelected', { table: 'users', selected: false })
      }
      resetUsers = true
    }, { immediate: true })

    return {
      groups,
      groupsChecked,
      resetGroups,
      users,
      usersChecked,
      resetUsers
    }
  },
  computed: {
    ...mapGetters([
      'getGroups',
      'getUsers'
    ])
  },
  components: {
    AllowedSelect
  }
}
</script>
