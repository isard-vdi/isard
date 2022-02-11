<template>
<b-container fluid class="justify-content-center pt-1 pt-lg-5 min-vh-100" style="background: #a7a5a7;">
  <b-row class="mt-2 lg-mt-5 pl-3 pr-3 h-100">
    <b-col cols="0" md="1" lg="2" class="h-100"></b-col>
    <b-col cols="12" md="10" lg="8" class="h-100">
      <b-row class="justify-content-center align-content-center h-100">
            <!-- HEADER -->
        <b-col sm="12" class="justify-content-center align-content-center d-flex right-separator-border rounded-top-30" style="background: #3a4445; height:100px;">
              <!-- logo -->
          <div id="logo-wrapper">
            <Logo/>
          </div>
            </b-col>
            <b-col class="px-0">
              <b-row style="background:#F7F7F7; padding-top: 100px;" class="m-0 rounded-bottom-30 pb-5">
                <!-- MACHINE INFO -->
                <b-col sm="12" class="text-center">
                  <!-- organitzation name -->
                  <h5 class="font-weight-bold text-medium-gray">{{ $t('views.direct-viewer.title') }}</h5>
                  <!-- machine name -->
                  <div v-if="!getDirectViewer.name && !(getDirectViewer.state === 'error')">
                    <span><h2>{{ `${$t('messages.loading')}` }}</h2><b-spinner></b-spinner></span>
                  </div>
                  <h1 class="font-weight-bold">{{ getDirectViewer.name }}</h1>
                  <!-- machine description -->
                  <h5 class="text-medium-gray">{{ getDirectViewer.description }}</h5>
                  <!-- machine status -->
                  <!--<div class="d-flex flex-col justify-content-center align-items-center mt-3">
                    <p class="mb-0 mr-3 text-medium-gray">Estado: {{machine_status}}</p>
                    <b-button v-if="machine_status == 'started'" size="sm" class="btn btn-red rounded-pill btn-secondary btn-sm">Parar</b-button>
                  </div>-->
                </b-col>
                <!-- MACHINE ACCESS METHODS -->
                <b-col sm="12" class="rounded-bottom-30 pt-3">
                  <!-- machine access methods  -->
                  <b-row class="justify-content-center">
                    <!-- single method start -->
                    <b-skeleton-wrapper :loading="loading" class='card-body pt-2 d-flex flex-row flex-wrap justify-content-center'>
                      <template #loading>
                         <DirectViewerSkeleton></DirectViewerSkeleton>
                         <DirectViewerSkeleton></DirectViewerSkeleton>
                      </template>
                      <b-col v-for="viewer in getDirectViewer.viewers" :key="viewer.kind + viewer.protocol" cols="8" md="5" lg="5" xl="4" class="m-2">
                        <div class="bg-white rounded-15 py-4 px-4 text-center">
                          <div style="height: 5rem; padding-top: 0.5rem">
                            <img :src="require(`../assets/img/icons/${getViewerData({kind: viewer.kind, protocol: viewer.protocol}).icon }.svg`)" alt="" style="max-inline-size: fit-content;">
                          </div>
                          <a :href="localClientInstructionsUrl" target="_blank">
                            <p v-if="viewer.kind === 'file'" v-b-tooltip="{ title: `${$t('views.direct-viewer.local-client-help')}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }" class="h4 cursor-pointer" style="position:absolute; top: 1.5rem; right: 2.3rem;">
                              <b-icon size="lg" icon="question-circle" variant="secondary"></b-icon>
                            </p>
                          </a>
                          <b-button class="mt-4 w-100 direct-viewer-button" @click="openDirectViewerDesktop(viewer)">{{getViewerData({kind: viewer.kind, protocol: viewer.protocol}).buttonText}}</b-button>
                        </div>
                      </b-col>
                    <!-- single method end -->
                    </b-skeleton-wrapper>
                  </b-row>
                  <!-- Powered By-->
                  <b-row id="powered-by" align-h="center">
                    <b-col class="text-center">
                      <PoweredBy/>
                    </b-col>
                  </b-row>
                </b-col>
              </b-row>
            </b-col>
          </b-row>
    </b-col>
    <b-col cols="0" md="1" lg="2" class="h-100"></b-col>
  </b-row>
</b-container>
</template>

<script>
import Logo from '@/components/Logo.vue'
import { mapGetters, mapActions } from 'vuex'
import { localClientInstructionsUrl } from '@/shared/constants'
import { computed } from '@vue/composition-api'
import DirectViewerSkeleton from '@/components/DirectViewerSkeleton.vue'
import PoweredBy from '@/components/shared/PoweredBy.vue'
import i18n from '@/i18n'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const loading = computed(() => $store.getters.getDirectViewer.viewers.length === 0)

    return {
      loading
    }
  },
  components: {
    Logo,
    DirectViewerSkeleton,
    PoweredBy
  },
  data () {
    return {
      machine_status: 'started',
      localClientInstructionsUrl
    }
  },
  computed: {
    ...mapGetters(['getDirectViewer'])
  },
  methods: {
    ...mapActions(['openDirectViewerDesktop']),
    getViewerData (payload) {
      const icons = {
        browser: {
          vnc: {
            icon: 'browser',
            buttonText: i18n.t('views.direct-viewer.button.browser')
          }
        },
        file: {
          spice: {
            icon: 'spice',
            buttonText: 'SPICE'
          }
        }
      }

      return icons[payload.kind][payload.protocol]
    }
  },
  beforeMount () {
    const token = this.$route.params.pathMatch
    this.$store.dispatch('getDirectViewers', { token })
  }
}
</script>

<style scoped>

#logo-wrapper {
  height: 110px;
  width: 110px;
  margin-top: 45px;
  position: relative;
  z-index: 9999;
  background-size: cover;
  background-repeat: no-repeat;
  background-position:center;
  background-color: #ffffff;
  border-radius: 50%;
  overflow: hidden;
  justify-content: center;
  display: flex;
  align-items: center;
}

.direct-viewer-button {
  border-radius: 7px;
  font-size: 0.8rem;
  background-color: #97c277;
  border-color: #97c277;
  color: black;
  font-size: 1rem;
}
</style>
