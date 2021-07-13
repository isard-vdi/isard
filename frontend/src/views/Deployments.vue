<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
    </div>
    <b-container fluid id="content">
      <div v-if="deployments_loaded && deployments.length === 0">
        <h3><strong>{{ $t('views.deployments.no-deployments.title') }}</strong></h3>
        <p>{{ $t('views.deployments.no-deployments.subtitle') }}</p>
      </div>
      <DeploymentsList v-else
        :deployments="deployments"
        :loading="!(deployments_loaded)"/>
    </b-container>
  </div>
</template>
<script>
// @ is an alias to /src
import NewNavBar from '@/components/NewNavBar.vue'
import DeploymentsList from '@/components/DeploymentsList.vue'

export default {
  components: {
    NewNavBar,
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
  }
}
</script>
