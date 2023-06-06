<template>
  <b-modal
    id="deploymentModal"
    v-model="modal.show"
    size="lg"
    :title="title"
    centered
    hide-footer
    :header-class="`bg-${modal.color}
    text-white`"
    @hidden="closeModal"
  >
    <span v-if="modal.type === 'visibility'">
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
    </span>
    <span v-else-if="modal.type === 'downloadCSV'">
      <b-row
        class="ml-2 my-2 pr-3"
      >
        <b-col
          cols="9"
          class="mt-2"
        >
          <p>
            {{ $t(`views.deployment.modal.option.keep-csv`) }}
          </p>
        </b-col>
        <b-col
          cols="3"
          class="mt-2 text-center"
        >
          <b-button
            :pill="true"
            class="bg-purple text-white"
            block
            size="sm"
            @click="downloadDirectViewerCSV(false)"
          >
            {{ $t(`views.deployment.modal.confirmation.keep-csv`) }}
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
            {{ $t(`views.deployment.modal.option.reset-csv`) }}
          </p>
        </b-col>
        <b-col
          cols="3"
          class="my-2 text-center"
        >
          <b-button
            :pill="true"
            class="bg-purple text-white"
            block
            size="sm"
            @click="downloadDirectViewerCSV(true)"
          >
            {{ $t(`views.deployment.modal.confirmation.reset-csv`) }}
          </b-button>
        </b-col>
      </b-row>
    </span>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const modal = computed(() => $store.getters.getDeploymentModal)

    const title = computed(() => {
      if (modal.value.type === 'visibility') {
        if (modal.value.item.visible) {
          return i18n.t('views.deployment.modal.title.make-invisible', { name: modal.value.item.name })
        } else {
          return i18n.t('views.deployment.modal.title.make-visible', { name: modal.value.item.name })
        }
      } else if (modal.value.type === 'downloadCSV') {
        return i18n.t('views.deployment.modal.title.download-csv', { name: modal.value.item.name })
      }

      return ''
    })

    const toggleVisibility = (stopStartedDomains) => {
      $store.dispatch('toggleVisible', { id: modal.value.item.id, visible: modal.value.item.visible, stopStartedDomains }).then(() => {
        closeModal()
      })
    }

    const downloadDirectViewerCSV = (reset) => {
      const data = { id: modal.value.item.id }
      if (reset) {
        data.reset = reset
      }
      $store.dispatch('downloadDirectViewerCSV', data).then(() => {
        closeModal()
      })
    }

    const closeModal = () => {
      $store.dispatch('resetDeploymentModal')
    }
    return {
      closeModal,
      modal,
      title,
      toggleVisibility,
      downloadDirectViewerCSV
    }
  }
}
</script>
