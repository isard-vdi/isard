<template>
  <b-modal
    id="deploymentModal"
    v-model="modal.show"
    size="lg"
    :title="title"
    centered
    :hide-footer="modal.type !== 'delete' && modal.type !== 'coOwners' && modal.type !== 'bastion'"
    :header-class="`bg-${modal.color}
    text-white`"
    @hidden="closeModal"
  >
    <span v-if="modal.type === 'visibility'">
      <span
        v-if="modal.item.visible"
      >
        <b-alert
          show
          variant="warning"
          class="ml-2 mb-2 pr-3"
        >
          <p
            class="mb-0"
          >
            {{ $t(`views.deployment.modal.body.invisible-warning`, { visible: desktopsVisible, invisible: desktopsInvisible }) }}
          </p>
        </b-alert>
        <hr>
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
      <span
        v-if="!modal.item.visible"
      >
        <b-alert
          show
          variant="warning"
          class="ml-2 mb-2 pr-3"
        >
          <p
            class="mb-0"
          >
            {{ $t(`views.deployment.modal.body.visible-warning`, { visible: desktopsVisible, invisible: desktopsInvisible }) }}
          </p>
        </b-alert>
        <hr>
        <b-row
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
              @click="toggleVisibility(false)"
            >
              {{ $t(`views.deployment.modal.confirmation.make-visible`) }}
            </b-button>
          </b-col>
        </b-row>
      </span>
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
    <span v-else-if="modal.type === 'delete'">
      <b-row
        v-if="!isOwner"
        class="mx-2 my-2 text-danger"
      >
        <b-alert
          show
          variant="danger"
          class="w-100"
        >
          <span>
            <b-icon
              class="mr-2"
              icon="exclamation-triangle-fill"
            />
            {{ $t('views.deployment.modal.body.co-owner-warning-delete') }}
          </span>
        </b-alert>
      </b-row>
      <span v-else>
        <b-row
          v-if="modal.type === 'delete'"
          class="ml-2 my-2 pr-3"
        >
          {{ $t('views.deployment.modal.body.text') }}
        </b-row>
        <b-row
          v-if="modal.type === 'delete'"
          class="ml-2 my-2 pr-3"
        >
          <b-col
            v-if="maxTime !== 0"
            cols="12"
          >
            <b-form-checkbox
              id="sendToRecycleBin"
              v-model="sendToRecycleBin"
              name="sendToRecycleBin"
              :value="true"
              :unchecked-value="false"
            >
              {{ $t('views.deployment.modal.body.send-to-recycle-bin') }}
              <span
                v-if="maxTime !== 'null'"
              >{{ `${$t("components.statusbar.recycle-bins.max-time", { time: maxTime })}` }}</span>
            </b-form-checkbox>
          </b-col>
        </b-row>
      </span>
    </span>
    <span v-else-if="modal.type === 'coOwners'">
      <DeploymentCoOwnersForm />
    </span>
    <span v-else-if="modal.type === 'bastion'">
      <div
        v-if="bastionLoading"
        class="text-center my-4"
      >
        <b-spinner />
      </div>
      <span v-else>
        <b-alert
          show
          variant="info"
          class="ml-2 mb-2 pr-3"
        >
          <p
            class="mb-0"
          >
            {{ $t('views.deployment.modal.body.bastion-info') }}
          </p>
        </b-alert>
        <b-row class="ml-2 my-2 pr-3">
          <b-col cols="6">
            <b-form-checkbox
              id="deploymentBastionSshEnabled"
              v-model="bastionForm.ssh.enabled"
              switch
            >
              {{ $t('forms.domain.bastion.ssh.checkbox') }}
            </b-form-checkbox>
          </b-col>
          <b-col
            v-if="bastionForm.ssh.enabled"
            cols="6"
          >
            <label for="deploymentBastionSshPort">{{ $t('forms.domain.bastion.ssh.port') }}</label>
            <b-form-input
              id="deploymentBastionSshPort"
              v-model.number="bastionForm.ssh.port"
              type="number"
              min="1"
              max="65535"
            />
          </b-col>
        </b-row>
        <hr>
        <b-row class="ml-2 my-2 pr-3">
          <b-col cols="6">
            <b-form-checkbox
              id="deploymentBastionHttpEnabled"
              v-model="bastionForm.http.enabled"
              switch
            >
              {{ $t('forms.domain.bastion.http.checkbox') }}
            </b-form-checkbox>
          </b-col>
          <b-col
            v-if="bastionForm.http.enabled"
            cols="3"
          >
            <label for="deploymentBastionHttpPort">{{ $t('forms.domain.bastion.http.http-port') }}</label>
            <b-form-input
              id="deploymentBastionHttpPort"
              v-model.number="bastionForm.http.http_port"
              type="number"
              min="1"
              max="65535"
            />
          </b-col>
          <b-col
            v-if="bastionForm.http.enabled"
            cols="3"
          >
            <label for="deploymentBastionHttpsPort">{{ $t('forms.domain.bastion.http.https-port') }}</label>
            <b-form-input
              id="deploymentBastionHttpsPort"
              v-model.number="bastionForm.http.https_port"
              type="number"
              min="1"
              max="65535"
            />
          </b-col>
        </b-row>
      </span>
    </span>
    <template
      #modal-footer
    >
      <span class="d-flex justify-content-end">
        <b-button
          class="mr-2"
          squared
          size="sm"
          @click="closeModal"
        >
          {{ $t('forms.cancel') }}
        </b-button>
        <b-button
          v-if="modal.type === 'delete' && isOwner"
          squared
          variant="outline-danger"
          size="sm"
          @click="deleteDeployment"
        >
          {{ $t(`views.deployment.modal.confirmation.delete`) }}
        </b-button>
        <b-button
          v-else-if="modal.type === 'coOwners' && isOwner"
          squared
          variant="green"
          size="sm"
          @click="updateCoOwners"
        >
          {{ $t(`views.deployment.modal.confirmation.co-owners`) }}
        </b-button>
        <b-button
          v-else-if="modal.type === 'bastion'"
          squared
          variant="primary"
          size="sm"
          :disabled="bastionLoading"
          @click="updateBastion"
        >
          {{ $t(`views.deployment.modal.confirmation.bastion`) }}
        </b-button>
      </span>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'
import i18n from '@/i18n'
import DeploymentCoOwnersForm from './DeploymentCoOwnersForm.vue'

export default {
  components: {
    DeploymentCoOwnersForm
  },
  setup (_, context) {
    const $store = context.root.$store
    const deployment = computed(() => $store.getters.getDeployment)
    const modal = computed(() => $store.getters.getDeploymentModal)
    const maxTime = computed(() => $store.getters.getMaxTime)

    const sendToRecycleBin = ref(false)
    $store.dispatch('fetchDefaultCheck').then(() => {
      sendToRecycleBin.value = $store.getters.getDefaultCheck
    })

    const title = computed(() => {
      if (modal.value.type === 'visibility') {
        if (modal.value.item.visible) {
          return i18n.t('views.deployment.modal.title.make-invisible', { name: modal.value.item.name })
        } else {
          return i18n.t('views.deployment.modal.title.make-visible', { name: modal.value.item.name })
        }
      } else if (modal.value.type === 'downloadCSV') {
        return i18n.t('views.deployment.modal.title.download-csv', { name: modal.value.item.name })
      } else if (modal.value.type === 'delete') {
        return i18n.t('views.deployment.modal.title.delete', { name: modal.value.item.name })
      } else if (modal.value.type === 'coOwners') {
        return i18n.t('views.deployment.modal.title.co-owners', { name: modal.value.item.name })
      } else if (modal.value.type === 'bastion') {
        return i18n.t('views.deployment.modal.title.bastion', { name: modal.value.item.name })
      }

      return ''
    })

    // Deployment-level bastion config: two toggles + ports. Loaded from the
    // deployment row when the modal opens; PUT applies it to every current
    // desktop's target and is inherited by new/recreated desktops at start.
    // Starts ``true`` so the form can't render (and take input) with default
    // values before the stored config arrives — the fetch watcher below only
    // fires after the modal is already visible.
    const bastionLoading = ref(true)
    const bastionForm = ref({
      ssh: { enabled: false, port: 22 },
      http: { enabled: false, http_port: 80, https_port: 443 }
    })

    watch(
      () => (modal.value.type === 'bastion' && modal.value.show) ? modal.value.item.id : null,
      (id) => {
        if (!id) return
        bastionLoading.value = true
        $store.dispatch('fetchDeploymentBastion', { id }).then((data) => {
          bastionForm.value = {
            ssh: { enabled: false, port: 22, ...(data.ssh || {}) },
            http: { enabled: false, http_port: 80, https_port: 443, ...(data.http || {}) }
          }
        }).catch(() => {
          // Error already toasted by the action.
        }).finally(() => {
          bastionLoading.value = false
        })
      },
      { immediate: true }
    )

    const updateBastion = () => {
      bastionLoading.value = true
      $store.dispatch('updateDeploymentBastion', {
        id: modal.value.item.id,
        ssh: bastionForm.value.ssh,
        http: bastionForm.value.http
      }).then(() => {
        closeModal()
      }).catch(() => {
        // Error already toasted by the action — keep the modal open.
      }).finally(() => {
        bastionLoading.value = false
      })
    }

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

    const deleteDeployment = () => {
      $store.dispatch('deleteDeployment', {
        id: modal.value.item.id,
        permanent: !sendToRecycleBin.value,
        pathName: 'deployments'
      }).then(() => {
        sendToRecycleBin.value = $store.getters.getDefaultCheck
        closeModal()
      }).catch(() => {
        // Error already toasted by the action — close the modal anyway so
        // the user isn't stuck on a frozen confirmation screen.
        closeModal()
      })
    }

    // ``isOwner`` MUST be a computed, not a plain function — Vue
    // evaluates ``v-if="isOwner"`` against the function reference
    // when it isn't called with ``()``, which is *always* truthy and
    // makes the "Update co-owners" footer button visible to every
    // viewer (including co-owners who are not the owner). Loading
    // ``fetchCoOwners`` lives in a watcher that fires when either the
    // co-owners modal or the delete modal opens, so the side effect
    // doesn't ride on the render. The delete modal also needs it: its
    // footer "Delete" button is gated on ``isOwner``, and opening the
    // delete modal from the deployments LIST (which doesn't eagerly
    // fetch co-owners) used to leave ``getCoOwners.owner`` empty →
    // ``isOwner=false`` → user saw a misleading "you're a co-owner"
    // warning and had no delete button.
    watch(
      () => (['coOwners', 'delete'].includes(modal.value.type)) ? modal.value.item.id : null,
      (id) => { if (id) $store.dispatch('fetchCoOwners', id) },
      { immediate: true }
    )

    const isOwner = computed(() => {
      const owner = $store.getters.getCoOwners?.owner
      if (!owner || !owner.id) return false
      return $store.getters.getUser?.user_id === owner.id
    })

    const updateCoOwners = () => {
      const selectedUsers = computed(() => $store.getters.getSelectedUsers)
      const users = selectedUsers.value.map(user => user.id)

      $store.dispatch('updateCoOwners', { id: modal.value.item.id, users: users }).then(() => {
        closeModal()
      })
    }

    const desktopsVisible = computed(() => {
      return deployment.value.desktops.filter(d => d.visible).length
    })
    const desktopsInvisible = computed(() => {
      return deployment.value.desktops.filter(d => !d.visible).length
    })

    const closeModal = () => {
      $store.dispatch('resetDeploymentModal')
    }
    return {
      closeModal,
      modal,
      title,
      toggleVisibility,
      downloadDirectViewerCSV,
      bastionLoading,
      bastionForm,
      updateBastion,
      deleteDeployment,
      updateCoOwners,
      maxTime,
      sendToRecycleBin,
      desktopsVisible,
      desktopsInvisible,
      isOwner
    }
  }
}
</script>
