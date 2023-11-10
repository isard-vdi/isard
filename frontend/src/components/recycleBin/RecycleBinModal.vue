<template>
  <b-modal
    id="recycleBinModal"
    v-model="modal.show"
    size="lg"
    :title="$t(`views.recycle-bin.modal.title.${modal.type}`)"
    centered
    hide-footer
    :header-class="`
    ${modal.type == 'restore' ? 'bg-green' : 'bg-red'}
     text-white`"
    @hidden="closeModal"
  >
    <b-row
      v-if="modal.type === 'restore'"
      class="ml-2 my-2 pr-3"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`views.recycle-bin.modal.option.restore`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="my-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-success"
          block
          size="sm"
          @click="restoreRecycleBin"
        >
          {{ $t(`views.recycle-bin.modal.confirmation.restore`) }}
        </b-button>
      </b-col>
    </b-row>
    <b-row
      v-if="modal.type === 'delete'"
      class="ml-2 my-2 pr-3"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`views.recycle-bin.modal.option.delete`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="my-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-danger"
          block
          size="sm"
          @click="deleteRecycleBin"
        >
          {{ $t(`views.recycle-bin.modal.confirmation.delete`) }}
        </b-button>
      </b-col>
    </b-row>
    <b-row
      v-if="modal.type === 'empty'"
      class="ml-2 my-2 pr-3"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`views.recycle-bin.modal.option.empty`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="my-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-danger"
          block
          size="sm"
          @click="emptyRecycleBin"
        >
          {{ $t(`views.recycle-bin.modal.confirmation.empty`) }}
        </b-button>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const modal = computed(() => $store.getters.getRecycleBinModal)
    const urlTokens = computed(() => $store.getters.getUrlTokens)

    const restoreRecycleBin = () => {
      $store.dispatch('restoreRecycleBin', { id: modal.value.item.id }).then(() => {
        closeModal()
        if (!checkLocation('recycleBins')) {
          $store.dispatch('navigate', 'recycleBins')
        }
      })
    }

    const emptyRecycleBin = () => {
      $store.dispatch('emptyRecycleBin', { id: modal.value.item.id }).then(() => {
        closeModal()
      })
    }

    const deleteRecycleBin = () => {
      $store.dispatch('deleteRecycleBin', { id: modal.value.item.id }).then(() => {
        closeModal()
        if (!checkLocation('recycleBins')) {
          $store.dispatch('navigate', 'recycleBins')
        }
      })
    }

    const closeModal = () => {
      $store.dispatch('resetRecycleBinModal')
    }

    const checkLocation = (location) => {
      const tokens = urlTokens.value
      return tokens === location
    }

    return {
      closeModal,
      modal,
      restoreRecycleBin,
      deleteRecycleBin,
      emptyRecycleBin
    }
  }
}
</script>
