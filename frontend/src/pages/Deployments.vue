<template>
  <b-container fluid id="content">
    <div v-if="deployments_loaded && deployments.length === 0">
      <h3><strong>{{ $t('views.deployments.no-deployments.title') }}</strong></h3>
      <p>{{ $t('views.deployments.no-deployments.subtitle') }}</p>
    </div>
    <DeploymentsList v-else
      :deployments="deployments"
      :loading="!(deployments_loaded)"/>
  </b-container>
</template>
<script>
// @ is an alias to /src
import DeploymentsList from '@/components/DeploymentsList.vue'

export default {
  components: {
    DeploymentsList
  },
  created () {
    this.$store.dispatch('fetchDeployments')
  },
  computed: {
    deployments () {
      return this.$store.getters.getDeployments
    },
    deployments_loaded () {
      return this.$store.getters.getDeploymentsLoaded
    }
  },
  mounted () {
    this.$store.dispatch('openSocket', { room: 'deployments' })
  },
  destroyed () {
    this.$store.dispatch('closeSocket')
  }
}
</script>
