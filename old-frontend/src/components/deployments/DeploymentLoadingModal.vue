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

    // ``deployment.totalDesktops`` is enriched by /videowall (apiv4
    // service ``DeploymentService.get_deployment``: ``len(create_dict)
    // * total_users``) and is the *expected* final count — independent
    // of how many ``deploymentdesktop_add`` WS events have arrived.
    // Prefer it over ``desktops.length`` so the modal shows e.g.
    // "2 of 32" immediately, not "2 of 3" because the early WS events
    // were dropped during the route+fetch race. Fall back to ``.length``
    // when ``totalDesktops`` isn't present (legacy shape).
    const desktopsTotal = computed(() =>
      deployment.value.totalDesktops || deployment.value.desktops.length
    )

    // "Created" = reached a terminal state (Stopped / Started /
    // WaitingIP / Failed). The deployment pipeline transitions a
    // desktop through several non-terminal intermediates — Creating,
    // CreatingDisk, ``working``, maintenance, ... — and the user
    // sees a smooth bar advance only when we treat every non-terminal
    // value as "still in progress" rather than singling out
    // ``creating`` (the early-Stage-1 substate). Matches the wider
    // watcher in Deployment.vue which keeps the modal open across
    // the whole Stage-1 + Stage-2 pipeline.
    const TERMINAL_STATES = [
      desktopStates.stopped,
      desktopStates.started,
      desktopStates.waitingip,
      desktopStates.failed
    ]
    const desktopsCreated = computed(() =>
      deployment.value.desktops.filter(d => {
        const s = (d.state || '').toLowerCase()
        return s && TERMINAL_STATES.includes(s)
      }).length
    )

    const desktopsCreatingLen = computed(() => desktopsTotal.value - desktopsCreated.value)

    const desktopsBadge = computed(() => {
      if (desktopsCreatingLen.value !== 0) {
        return i18n.t('views.deployment.loading-modal.body.desktops-total-creating', {
          total: desktopsTotal.value,
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
