<template>
  <b-modal
    id="allowedModal"
    v-model="showAllowedModal"
    size="lg"
    :title="$t(`forms.allowed.modal.title`)"
    centered
    @hidden="closeAllowedModal"
  >
    <slot name="subtitle" />
    <div class="ml-4 mr-4">
      <AllowedForm />
    </div>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          variant="primary"
          class="float-right"
          @click="updateAllowed"
        >
          {{ $t(`forms.allowed.modal.buttons.update`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import AllowedForm from '@/components/AllowedForm.vue'
import { map } from 'lodash'

export default {
  components: { AllowedForm },
  setup (_, context) {
    const $store = context.root.$store

    const selectedGroups = computed(() => $store.getters.getSelectedGroups)
    const groupsChecked = computed(() => $store.getters.getGroupsChecked)
    const selectedUsers = computed(() => $store.getters.getSelectedUsers)
    const usersChecked = computed(() => $store.getters.getUsersChecked)

    const showAllowedModal = computed({
      get: () => $store.getters.getShowAllowedModal,
      set: (value) => $store.commit('setShowAllowedModal', value)
    })

    const updateAllowed = () => {
      const groups = groupsChecked.value ? map(selectedGroups.value, 'id') : false
      const users = usersChecked.value ? map(selectedUsers.value, 'id') : false
      context.emit('updateAllowed', { groups, users })
      closeAllowedModal()
    }

    const closeAllowedModal = () => {
      $store.dispatch('resetAllowedState')
      $store.dispatch('showAllowedModal', false)
    }

    return { showAllowedModal, updateAllowed, closeAllowedModal }
  }
}
</script>
