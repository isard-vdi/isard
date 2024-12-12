<template>
  <b-modal
    id="importUserModal"
    v-model="showImportUserModal"
    size="lg"
    :title="$t(`forms.import.modal.title`)"
    header-class="bg-orange text-white"
    centered
    @hidden="closeImportUserModal"
  >
    <b-row
      class="ml-2 mr-2"
    >
      <b-col cols="12">
        <h5>
          {{ $t(`forms.import.modal.description`) }}
        </h5>
        <b-row
          class="m-3"
        >
          <p>
            {{ $t(`forms.import.modal.migration-instructions1`) }}
          </p>
          <p>
            {{ $t(`forms.import.modal.migration-instructions2`) }}
          </p>
          <p>
            {{ $t(`forms.import.modal.migration-instructions3`) }}
          </p>
        </b-row>
        <b-input-group
          class="mt-3"
        >
          <b-form-input
            id="importToken"
            v-model="importToken"
            :placeholder="$t(`forms.import.modal.placeholder`)"
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
          :title="$t(`forms.import.modal.migrate-tooltip`)"
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
