<template>
  <b-container fluid id='content'>
    <template v-if="getViewType === 'grid'">
      <h5 class='font-weight-bold'>{{ getDeployment.name }}</h5>
      <hr class="mb-0"/>
      <b-row class='pb-3 pt-2 scrollable-div'>
        <DeploymentCard :key='desktop.id' v-for='desktop in visibleDesktops' :desktop="desktop" />
      </b-row>
    </template>
    <template v-else>
      <div v-if='getSelectedDesktop && getSelectedDesktop.viewer'>
        <h5 class='font-weight-bold'>{{ getSelectedDesktop.userName }} - {{ getDeployment.desktopName }}</h5>
        <NoVNC
          :height="'750px'"
          :desktop='getSelectedDesktop'
          :viewOnly='false'
          :qualityLevel='6'
        />
      </div>
      <div v-else>
        <h5 class='font-weight-bold'>{{ getSelectedDesktop.userName }} - {{ getDeployment.desktopName }}</h5>
        <div style="height: 750px; background-color: black; padding-top: 250px" class="cursor-pointer">
          <div id="deployment-logo" class="rounded-circle bg-red mx-auto d-block align-items-center " style="background-image: url(/custom/logo.svg);background-size: 70px 70px; opacity: 0.5;">
          </div>
          <p class="text-center text-white">{{ $t('views.deployment.desktop.not-available') }}</p>
        </div>
      </div>
    </template>
  </b-container>
</template>
<script>
// @ is an alias to /src
import NoVNC from '@/components/NoVNC.vue'
import DeploymentCard from '@/components/deployments/DeploymentCard.vue'
import { mapGetters } from 'vuex'

export default {
  components: {
    NoVNC,
    DeploymentCard
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
    this.$store.dispatch('setSelectedDesktop', this.getDeployment.desktops[0])
  },
  computed: {
    ...mapGetters(['getDeployment', 'getDeploymentLoaded', 'getViewType', 'getSelectedDesktop', 'getDeploymentsShowStarted']),
    sortedDesktops () {
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return d.viewer ? -1 : 1
      })
    },
    visibleDesktops () {
      return this.sortedDesktops.filter(desktop => this.getDeploymentsShowStarted === true ? desktop.state.toLowerCase() === 'started' : true)
    }
  }
}
</script>
