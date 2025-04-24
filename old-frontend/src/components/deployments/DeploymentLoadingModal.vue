<template>
  <b-modal
    id="deploymentLoadingModal"
    v-model="showDeploymentLoadingModal"
    size="lg"
    centered
    hide-footer
    @hidden="closeDeploymentLoadingModal"
  >
    <template #modal-title>
      <!-- eslint-disable-next-line vue/singleline-html-element-content-newline -->
      <h5 class="animated-elipsis modal-title">{{ $t('views.deployment.loading-modal.title', { name: deployment.name }) }}</h5>
    </template>
    <b-row
      class="mx-2"
    >
      <b-col cols="12">
        <b-row
          align-h="center"
          class="mb-4"
        >
          <!-- <img
            src=""
            alt="loading animation"
            style="max-height: 50vh;"
          > -->
        </b-row>

        <h5>
          {{ $t('views.deployment.loading-modal.body.title') }}
        </h5>
        <p>
          {{ desktopsBadge }}
        </p>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'
import { desktopStates } from '@/shared/constants'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const deployment = computed(() => $store.getters.getDeployment)

    const showDeploymentLoadingModal = computed({
      get: () => $store.getters.getShowDeploymentLoadingModal,
      set: (value) => $store.commit('setShowDeploymentLoadingModal', value)
    })

    const desktopsCreatingLen = computed(() => {
      return deployment.value.desktops.filter(d => [desktopStates.creating].includes(d.state.toLowerCase())).length
    })

    const desktopsBadge = computed(() => {
      if (desktopsCreatingLen.value !== 0) {
        return i18n.t('views.deployment.loading-modal.body.desktops-total-creating', {
          total: deployment.value.desktops.length,
          creating: desktopsCreatingLen.value
        })
      } else {
        return i18n.t('views.deployment.loading-modal.body.desktops-created')
      }
    })

    const closeDeploymentLoadingModal = () => {
      $store.dispatch('showDeploymentLoadingModal', false)
    }

    return {
      showDeploymentLoadingModal,
      closeDeploymentLoadingModal,
      deployment,
      desktopsBadge,
      desktopsCreatingLen
    }
  }
}
</script>
