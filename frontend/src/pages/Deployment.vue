<template>
  <b-container fluid id='content'>
    <h5 class='font-weight-bold'>
      {{ getDeployment.name }}
      <b-badge :variant="badgeVariant">{{ badgeText }}</b-badge>
    </h5>
    <hr class="mb-0"/>
    <b-alert show :class="deploymentVariant" class="mt-3">
      {{ $t('views.deployment.visibility-warning', { visibility: badgeText.toLowerCase() }) }}
    </b-alert>
    <DeploymentDesktopsList
      :desktops="sortedDesktops"
      :loading="!getDeploymentLoaded"
      :visible="getDeployment.visible">
    </DeploymentDesktopsList>
  </b-container>
</template>
<script>
// @ is an alias to /src
import DeploymentDesktopsList from '@/components/deployments/DeploymentDesktopsList.vue'
import { mapGetters } from 'vuex'
import { desktopStates } from '@/shared/constants'
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  setup (props, context) {
    const $store = context.root.$store

    const deployment = computed(() => $store.getters.getDeployment)
    const badgeVariant = computed(() => deployment.value.visible ? 'success' : 'danger')

    const deploymentVariant = computed(() => deployment.value.visible ? 'visibleHighlight' : 'alert-danger')

    const badgeText = computed(() => deployment.value.visible ? i18n.t('views.deployment.visibility.visible') : i18n.t('views.deployment.visibility.not-visible'))

    return {
      deployment,
      badgeVariant,
      badgeText,
      deploymentVariant
    }
  },
  components: {
    DeploymentDesktopsList
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
  },
  computed: {
    ...mapGetters(['getDeployment', 'getDeploymentLoaded']),
    sortedDesktops () {
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase()) ? -1 : 1
      })
    }
  }
}
</script>
