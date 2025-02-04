<template>
  <b-container
    id="content"
    fluid
  >
    <template v-if="viewType === 'grid'">
      <h5 class="font-weight-bold">
        {{ deployment.name }}
      </h5>
      <hr>
      <b-alert
        show
        variant="info"
        class="m-2"
      >
        <b-icon
          class="mr-2"
          icon="info-circle-fill"
        />
        {{ $t('views.deployment.videowall.gpu-warning') }}
      </b-alert>
      <b-row class="pb-3 scrollable-div">
        <DeploymentCard
          v-for="desktop in filteredDesktops"
          :key="desktop.id"
          :desktop="desktop"
        />
      </b-row>
    </template>
    <template v-else>
      <div v-if="selectedDesktop && selectedDesktop.viewer">
        <h5 class="font-weight-bold">
          {{ selectedDesktop.userName }} - {{ deployment.desktopName }}
        </h5>
        <NoVNC
          :height="'750px'"
          :desktop="selectedDesktop"
          :view-only="false"
          :quality-level="6"
        />
      </div>
      <div v-else>
        <h5 class="font-weight-bold">
          {{ selectedDesktop.userName }} - {{ deployment.desktopName }}
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
import { onUnmounted, computed } from '@vue/composition-api'
import { desktopStates } from '@/shared/constants'

export default {
  components: {
    NoVNC,
    DeploymentCard
  },
  setup (props, context) {
    const $store = context.root.$store
    const deployment = computed(() => $store.getters.getDeployment)
    const filterDesktopsText = computed(() => $store.getters.getDesktopsFilter)
    const showStarted = computed(() => $store.getters.getDeploymentsShowStarted)
    const viewType = computed(() => $store.getters.getViewType)
    const selectedDesktop = computed(() => $store.getters.getSelectedDesktop)

    $store.dispatch('fetchDeployment', { id: context.root.$route.params.id })
    $store.dispatch('setSelectedDesktop', deployment.value.desktops[0])

    const sortedDesktops = computed(() => {
      return deployment.value.desktops.slice().sort(d => {
        // return started desktops first
        return d.viewer ? -1 : 1
      })
    })
    const visibleDesktops = computed(() => sortedDesktops.value.filter(desktop => showStarted.value === true ? [desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(desktop.state.toLowerCase()) : true))
    const filteredDesktops = computed(() => visibleDesktops.value.filter(desktop => desktop.userName.toLowerCase().includes(filterDesktopsText.value.toLowerCase())))

    onUnmounted(() => {
      $store.dispatch('resetDeploymentState')
    })

    return {
      deployment,
      viewType,
      selectedDesktop,
      filteredDesktops
    }
  }
}
</script>
