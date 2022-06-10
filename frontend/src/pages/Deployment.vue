<template>
  <b-container fluid id='content'>
    <h5 class='font-weight-bold'>{{ getDeployment.name }}</h5>
    <hr class="mb-0"/>
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

export default {
  components: {
    DeploymentDesktopsList
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
  },
  computed: {
    ...mapGetters(['getDeployment', 'getDeploymentLoaded']),
    sortedDesktops () {
      console.log(this.getDeployment)
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase()) ? -1 : 1
      })
    }
  }
}
</script>
