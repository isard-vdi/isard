<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
    </div>
    <b-container fluid id="content">
      <h5 class='font-weight-bold'>{{ this.$route.params.id }}</h5>
      <b-row class='pb-3 pt-2' v-if="deployment.filter(d => d.viewer).length !== 0">
        <b-col cols='3' :key="desktop.id" v-for="desktop in deployment">
          <NoVNC v-if="desktop.viewer"
            :height="'200px'"
            :desktop="desktop"/>
        </b-col>
      </b-row>
      <h3 v-else><strong>{{ $t('views.deployment.no-started-desktops.title') }}</strong></h3>
    </b-container>
  </div>
</template>
<script>
// @ is an alias to /src
import NewNavBar from '@/components/NewNavBar.vue'
import NoVNC from '@/components/NoVNC.vue'

export default {
  components: {
    NewNavBar,
    NoVNC
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
  },
  computed: {
    deployment () {
      return this.$store.getters.getDeployment
    },
    deployment_loaded () {
      return this.$store.getters.getDeploymentLoaded
    }
  }
}
</script>
