<template>
  <b-container
    id="content"
    fluid
  >
    <div v-if="deployments_loaded && getDeployments.length === 0">
      <h3><strong>{{ $t('views.deployments.no-deployments.title') }}</strong></h3>
      <p>{{ $t('views.deployments.no-deployments.subtitle') }}</p>
    </div>
    <DeploymentsList
      v-else
      :deployments="sortedDeployments"
      :loading="!(deployments_loaded)"
    />
  </b-container>
</template>
<script>
// @ is an alias to /src
import DeploymentsList from '@/components/deployments/DeploymentsList.vue'
import { mapGetters } from 'vuex'

export default {
  components: {
    DeploymentsList
  },
  computed: {
    ...mapGetters(['getDeployments']),
    sortedDeployments () {
      return this.getDeployments.slice().sort(d => {
        // return visible deployments first
        return d.visible ? -1 : 1
      })
    },
    deployments_loaded () {
      return this.$store.getters.getDeploymentsLoaded
    }
  },
  created () {
    this.$store.dispatch('fetchDeployments')
  },
  destroyed () {
    this.$store.dispatch('resetDeploymentsState')
  }
}
</script>
