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
        <p class="mb-3">
          {{ $t('views.deployment.loading-modal.body.title') }}
        </p>

        <!-- Stage 1: Engine fans out rows into the deployment.
             Active between ``creating_desktops`` and ``end_creating_desktops``
             (the engine's ``new_from_templateTh.process_desktops`` envelope)
             OR while fewer rows have arrived than the deployment expects. -->
        <div class="mb-3">
          <h6 class="d-flex align-items-center mb-1">
            <b-icon
              v-if="stage1Done"
              icon="check-circle-fill"
              variant="success"
              class="mr-2"
            />
            <b-spinner
              v-else-if="stage1Active"
              small
              class="mr-2"
            />
            <b-icon
              v-else
              icon="circle"
              class="text-muted mr-2"
            />
            <span>{{ $t('views.deployment.loading-modal.body.stage1-title') }}</span>
          </h6>
          <small class="text-muted">{{ stage1Status }}</small>
          <b-progress
            v-if="desktopsTotal > 0"
            :max="desktopsTotal"
            :value="stage1Value"
            :animated="stage1Active"
            :striped="stage1Active"
            :variant="stage1Done ? 'success' : 'primary'"
            height="1.2rem"
            show-progress
            class="mt-1"
          />
        </div>

        <!-- Stage 2: storage tasks turn ``Creating`` rows into ``Stopped``.
             Active whenever rows have arrived AND not all of them are
             terminal yet. Storage tasks run in parallel with the Stage-1
             fan-out loop, so this bar can advance before Stage 1 completes
             — but the status text stays "pending" while desktops.length=0. -->
        <div>
          <h6 class="d-flex align-items-center mb-1">
            <b-icon
              v-if="stage2Done"
              icon="check-circle-fill"
              variant="success"
              class="mr-2"
            />
            <b-spinner
              v-else-if="stage2Active"
              small
              class="mr-2"
            />
            <b-icon
              v-else
              icon="circle"
              class="text-muted mr-2"
            />
            <span>{{ $t('views.deployment.loading-modal.body.stage2-title') }}</span>
          </h6>
          <small class="text-muted">{{ stage2Status }}</small>
          <b-progress
            v-if="desktopsTotal > 0"
            :max="desktopsTotal"
            :value="stage2Value"
            :animated="stage2Active"
            :striped="stage2Active"
            :variant="stage2Done ? 'success' : 'primary'"
            height="1.2rem"
            show-progress
            class="mt-1"
          />
        </div>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'
import { desktopStates } from '@/shared/constants'

// Backend status values that mean "this desktop is fully provisioned".
// Matches the gate in Deployment.vue so the two views report consistent
// counts.
const TERMINAL_STATES = [
  desktopStates.stopped,
  desktopStates.started,
  desktopStates.waitingip,
  desktopStates.failed
]

export default {
  setup (_, context) {
    const $store = context.root.$store

    const deployment = computed(() => $store.getters.getDeployment)

    const showDeploymentLoadingModal = computed({
      get: () => $store.getters.getShowDeploymentLoadingModal,
      set: (value) => $store.commit('setShowDeploymentLoadingModal', value)
    })

    // ``totalDesktops`` is the expected final count, enriched by
    // ``DeploymentService.get_deployment_videowall`` as
    // ``len(create_dict) * total_users``. Falls back to ``desktops.length``
    // only when genuinely absent (e.g. before fetchDeployment resolves).
    const desktopsTotal = computed(() =>
      deployment.value.totalDesktops || (deployment.value.desktops || []).length || 0
    )
    const desktopsArrived = computed(() =>
      deployment.value.desktops ? deployment.value.desktops.length : 0
    )
    const desktopsInTerminal = computed(() =>
      (deployment.value.desktops || []).filter(d => {
        const s = (d.state || '').toLowerCase()
        return s && TERMINAL_STATES.includes(s)
      }).length
    )

    const isBulkCreating = computed(() =>
      !!deployment.value.id && $store.getters.isDeploymentBulkCreating(deployment.value.id)
    )

    // Stage 1 — engine fan-out (DB row inserts).
    //   active: bulk-spawn envelope OR fewer rows than expected
    //   done:   not in bulk-spawn AND all expected rows arrived
    const stage1Active = computed(() =>
      desktopsTotal.value > 0 && (isBulkCreating.value || desktopsArrived.value < desktopsTotal.value)
    )
    const stage1Done = computed(() =>
      desktopsTotal.value > 0 && !isBulkCreating.value && desktopsArrived.value >= desktopsTotal.value
    )
    const stage1Value = computed(() =>
      Math.min(desktopsArrived.value, desktopsTotal.value)
    )

    // Stage 2 — storage provisioning (qcow creation; status: Creating → Stopped).
    //   active: at least one row exists AND not every expected row is terminal
    //   done:   every expected row has reached a terminal state
    const stage2Active = computed(() =>
      desktopsTotal.value > 0 &&
      desktopsArrived.value > 0 &&
      desktopsInTerminal.value < desktopsTotal.value
    )
    const stage2Done = computed(() =>
      desktopsTotal.value > 0 && desktopsInTerminal.value >= desktopsTotal.value
    )
    const stage2Value = computed(() => desktopsInTerminal.value)

    const stage1Status = computed(() => {
      if (desktopsTotal.value === 0) {
        return i18n.t('views.deployment.loading-modal.body.stage1-pending')
      }
      if (stage1Done.value) {
        return i18n.t('views.deployment.loading-modal.body.stage1-done', { total: desktopsTotal.value })
      }
      return i18n.t('views.deployment.loading-modal.body.stage1-progress', {
        current: stage1Value.value,
        total: desktopsTotal.value
      })
    })

    const stage2Status = computed(() => {
      if (desktopsArrived.value === 0) {
        return i18n.t('views.deployment.loading-modal.body.stage2-pending')
      }
      if (stage2Done.value) {
        return i18n.t('views.deployment.loading-modal.body.stage2-done', { total: desktopsTotal.value })
      }
      return i18n.t('views.deployment.loading-modal.body.stage2-progress', {
        current: stage2Value.value,
        total: desktopsTotal.value
      })
    })

    const closeDeploymentLoadingModal = () => {
      $store.dispatch('showDeploymentLoadingModal', false)
    }

    return {
      showDeploymentLoadingModal,
      closeDeploymentLoadingModal,
      deployment,
      desktopsTotal,
      stage1Active,
      stage1Done,
      stage1Value,
      stage1Status,
      stage2Active,
      stage2Done,
      stage2Value,
      stage2Status
    }
  }
}
</script>
