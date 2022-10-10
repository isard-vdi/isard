<template>
  <b-container
    id="content"
    fluid
  >
    <template v-if="getViewType === 'grid'">
      <h5 class="font-weight-bold">
        {{ getDeployment.name }}
      </h5>
      <hr class="mb-0">
      <b-row class="pb-3 pt-2 scrollable-div">
        <DeploymentCard
          v-for="desktop in visibleDesktops"
          :key="desktop.id"
          :desktop="desktop"
        />
      </b-row>
    </template>
    <template v-else>
      <div v-if="getSelectedDesktop && getSelectedDesktop.viewer">
        <h5 class="font-weight-bold">
          {{ getSelectedDesktop.userName }} - {{ getDeployment.desktopName }}
        </h5>
        <NoVNC
          :height="'750px'"
          :desktop="getSelectedDesktop"
          :view-only="false"
          :quality-level="6"
        />
      </div>
      <div v-else>
        <h5 class="font-weight-bold">
          {{ getSelectedDesktop.userName }} - {{ getDeployment.desktopName }}
        </h5>
        <div
          style="height: 750px; background-color: black; padding-top: 250px"
          class="cursor-pointer"
        >
          <div
            id="deployment-logo"
            class="rounded-circle bg-red mx-auto d-block align-items-center "
            style="background-image: url(/custom/logo.svg);background-size: 70px 70px; opacity: 0.5;"
          />
          <p class="text-center text-white">
            {{ $t('views.deployment.desktop.not-available') }}
          </p>
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
import { onUnmounted } from '@vue/composition-api'

export default {
  components: {
    NoVNC,
    DeploymentCard
  },
  setup (props, context) {
    const $store = context.root.$store

    onUnmounted(() => {
      $store.dispatch('resetDeploymentState')
    })
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
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
    this.$store.dispatch('setSelectedDesktop', this.getDeployment.desktops[0])
  }
}
</script>
