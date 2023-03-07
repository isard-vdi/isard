<template>
  <b-modal
    id="visibilityModal"
    v-model="modal.show"
    size="lg"
    :title="$t(modal.item.visible ? 'views.deployment.modal.title.make-invisible' : 'views.deployment.modal.title.make-visible', { name: 'test deploy'})"
    centered
    hide-footer
    header-class="
    bg-blue
    text-white"
    @hidden="closeModal"
  >
    <span
      v-if="modal.item.visible"
    >
      <b-row
        class="ml-2 my-2 pr-3"
      >
        <b-col
          cols="9"
          class="mt-2"
        >
          <p>
            {{ $t(`views.deployment.modal.option.dont-stop-desktops`) }}
          </p>
        </b-col>
        <b-col
          cols="3"
          class="mt-2 text-center"
        >
          <b-button
            :pill="true"
            variant="outline-primary"
            block
            size="sm"
            @click="toggleVisibility(false)"
          >
            {{ $t(`views.deployment.modal.confirmation.dont-stop`) }}
          </b-button>
        </b-col>
      </b-row>
      <hr>

      <b-row
        class="ml-2 my-2 pr-3"
      >
        <b-col
          cols="9"
          class="mt-2"
        >
          <p>
            {{ $t(`views.deployment.modal.option.stop-desktops`) }}
          </p>
        </b-col>
        <b-col
          cols="3"
          class="my-2 text-center"
        >
          <b-button
            :pill="true"
            variant="outline-primary"
            block
            size="sm"
            @click="toggleVisibility(true)"
          >
            {{ $t(`views.deployment.modal.confirmation.stop`) }}
          </b-button>
        </b-col>
      </b-row>
    </span>
    <b-row
      v-if="!modal.item.visible"
      class="ml-2 my-2 pr-3"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`views.deployment.modal.option.make-visible`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="my-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-primary"
          block
          size="sm"
          @click="toggleVisibility"
        >
          {{ $t(`views.deployment.modal.confirmation.make-visible`) }}
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
    const modal = computed(() => $store.getters.getVisibilityModal)
    const toggleVisibility = (stopStartedDomains) => {
      $store.dispatch('toggleVisible', { id: modal.value.item.id, visible: modal.value.item.visible, stopStartedDomains }).then(() => {
        closeModal()
      })
    }
    const closeModal = () => {
      $store.dispatch('resetVisibilityModal')
    }
    return {
      closeModal,
      modal,
      toggleVisibility
    }
  }
}
</script>
