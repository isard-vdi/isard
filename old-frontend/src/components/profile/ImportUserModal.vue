<template>
  <b-modal
    id="importUserModal"
    v-model="showImportUserModal"
    size="lg"
    :title="$t(`forms.import.modal.title`)"
    centered
    @hidden="closeImportUserModal"
  >
    <b-row
      class="ml-2 mr-2"
    >
      <b-col cols="12">
        <p>
          {{ $t(`forms.import.modal.description`) }}
        </p>
        <b-input-group
          class="mt-3"
        >
          <b-form-input
            id="importToken"
            v-model="importToken"
            type="text"
          />
        </b-input-group>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          variant="primary"
          class="float-right"
          @click="submitForm"
        >
          {{ $t(`forms.import.modal.buttons.migrate`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const importToken = ref('')

    const showImportUserModal = computed({
      get: () => $store.getters.getShowImportUserModal,
      set: (value) => $store.commit('setShowImportUserModal', value)
    })

    const closeImportUserModal = () => {
      $store.dispatch('resetImportTokenState')
      $store.dispatch('showImportUserModal', false)
    }

    const submitForm = () => {
      $store.dispatch('importUser', { token: importToken.value })
    }

    return { importToken, showImportUserModal, closeImportUserModal, submitForm }
  }
}
</script>
