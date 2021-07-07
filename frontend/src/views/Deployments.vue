<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
    </div>
    <b-container fluid id="content">
      <DeploymentsList
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
