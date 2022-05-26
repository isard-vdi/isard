<template>
  <b-container fluid id='content'>
    <h5 class='font-weight-bold'>{{ getDeployment.name }}</h5>
    <hr class="mb-0"/>
    <DeploymentDesktopsList
      :desktops="sortedDesktops"
      :loading="!getDeploymentLoaded">
    </DeploymentDesktopsList>
  </b-container>
</template>
<script>
// @ is an alias to /src
import DeploymentDesktopsList from '@/components/deployments/DeploymentDesktopsList.vue'
import { mapGetters } from 'vuex'

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
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return d.viewer ? -1 : 1
      })
    }
  },
  mounted () {
    this.$store.dispatch('openSocket', { room: 'deploymentdesktops', deploymentId: this.$route.params.id })
  },
  destroyed () {
    this.$store.dispatch('closeSocket')
  }
}
</script>
