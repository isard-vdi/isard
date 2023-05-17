<template>
  <b-container
    fluid
    class="h-100 w-100 pt-4 scrollable-div"
    style="background: #a7a5a7;"
  >
    <b-row class="h-100 justify-content-center ml-2 mr-2 mr-md-5">
      <b-col
        class="pb-4"
        cols="12"
        md="10"
        lg="10"
      >
        <b-row class="justify-content-center align-content-center h-100">
          <!-- HEADER -->
          <b-col
            sm="12"
            class="justify-content-center align-content-center d-flex right-separator-border rounded-top-30"
            style="background: #3a4445; height:100px;"
          >
            <!-- logo -->
            <div id="logo-wrapper">
              <Logo />
            </div>
          </b-col>
          <b-col class="px-0">
            <b-row
              class="m-0 rounded-bottom-30 bg-lightgray"
            >
              <ResetModal />
              <DesktopButton
                v-if="!loading"
                class="card-button mt-3 ml-4"
                :active="true"
                button-class="btn-red"
                :spinner-active="false"
                :butt-text="$t(`views.select-template.status.${status['restart'].action}.text`)"
                :icon-name="status['restart'].icon"
                @buttonClicked="resetDesktop(status['restart'].action)"
              />
              <!-- MACHINE INFO -->
              <b-col
                sm="12"
                class="text-center mt-4"
              >
                <!-- organitzation name -->
                <h5 class="font-weight-bold text-medium-gray">
                  {{ $t('views.direct-viewer.title') }}
                </h5>
                <!-- machine name -->
                <div v-if="!directViewer.name && !(directViewer.state === 'error')">
                  <span><h2>{{ `${$t('messages.loading')}` }}</h2><b-spinner /></span>
                </div>
                <h1 class="font-weight-bold">
                  {{ directViewer.name }}
                </h1>
                <!-- machine shutdown -->
                <h4
                  v-if="directViewer.shutdown"
                  class="text-medium-gray"
                >
                  {{ directViewer.shutdown }}
                </h4>
                <!-- machine description -->
                <h5 class="text-medium-gray">
                  {{ directViewer.description }}
                </h5>
              </b-col>
              <!-- MACHINE ACCESS METHODS -->
              <b-col
                cols="12"
                class="rounded-bottom-30 pt-3"
              >
                <!-- machine access methods  -->
                <b-row class="justify-content-center">
                  <!-- single method start -->
                  <b-skeleton-wrapper
                    :loading="loading"
                    class="card-body pt-2 d-flex flex-row flex-wrap justify-content-center"
                  >
                    <template #loading>
                      <DirectViewerSkeleton />
                      <DirectViewerSkeleton />
                    </template>
                    <b-col sm="10">
                      <b-row class="justify-content-center text-center">
                        <!-- Browser viewers -->
                        <b-col
                          v-if="browserViewers.length"
                          xl="6"
                        >
                          <h6 class="font-weight-bold text-medium-gray">
                            {{ $t('views.direct-viewer.browser.title') }}
                          </h6>
                          <div class="column-header d-flex align-items-center justify-content-center">
                            <p>{{ $t('views.direct-viewer.browser.subtitle') }}</p>
                          </div>
                          <DirectViewerButton
                            v-for="viewer in browserViewers"
                            :key="viewer.kind + viewer.protocol"
                            :direct-viewer="directViewer"
                            :viewer="viewer"
                            :viewer-description="viewerDescription[viewer.protocol]"
                          />
                        </b-col>
                        <!-- Client viewers -->
                        <DirectViewerHelpSpice />
                        <DirectViewerHelpRDP />
                        <b-col
                          v-if="fileViewers.length"
                          xl="6"
                        >
                          <h6 class="font-weight-bold text-medium-gray">
                            {{ $t('views.direct-viewer.file.title') }}
                          </h6>
                          <div class="column-header d-flex align-items-center justify-content-center">
                            <p>{{ $t('views.direct-viewer.file.subtitle') }}</p>
                          </div>
                          <DirectViewerButton
                            v-for="viewer in fileViewers"
                            :key="viewer.kind + viewer.protocol"
                            :direct-viewer="directViewer"
                            :viewer="viewer"
                            :viewer-description="viewerDescription[viewer.protocol]"
                          />
                        </b-col>
                      </b-row>
                    </b-col>
                    <!-- single method end -->
                  </b-skeleton-wrapper>
                </b-row>
                <!-- Powered By-->
                <b-row
                  id="powered-by"
                  align-h="center"
                >
                  <b-col class="text-center">
                    <PoweredBy />
                  </b-col>
                </b-row>
              </b-col>
            </b-row>
          </b-col>
        </b-row>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import Logo from '@/components/Logo.vue'
import { computed, watch } from '@vue/composition-api'
import DirectViewerSkeleton from '@/components/directViewer/DirectViewerSkeleton.vue'
import DirectViewerButton from '@/components/directViewer/DirectViewerButton.vue'
import PoweredBy from '@/components/shared/PoweredBy.vue'
import DirectViewerHelpSpice from '@/components/directViewer/DirectViewerHelpSpice.vue'
import DirectViewerHelpRDP from '@/components/directViewer/DirectViewerHelpRDP.vue'
import i18n from '@/i18n'
import { desktopStates, status } from '@/shared/constants'
import DesktopButton from '@/components/desktops/Button.vue'
import ResetModal from '@/components/directViewer/ResetModal.vue'

export default {
  components: {
    Logo,
    DirectViewerSkeleton,
    PoweredBy,
    DirectViewerButton,
    DirectViewerHelpSpice,
    DirectViewerHelpRDP,
    DesktopButton,
    ResetModal
  },
  setup (props, context) {
    const $store = context.root.$store
    const loading = computed(() => $store.getters.getDirectViewer.viewers.length === 0)
    const directViewer = computed(() => $store.getters.getDirectViewer)
    const browserViewers = computed(() => directViewer.value.viewers.filter(viewer => viewer.kind === 'browser'))
    const fileViewers = computed(() => directViewer.value.viewers.filter(viewer => viewer.kind === 'file'))
    const viewerDescription = {
      spice: i18n.t('views.direct-viewer.description.spice'),
      vnc: i18n.t('views.direct-viewer.description.vnc'),
      rdp: i18n.t('views.direct-viewer.description.rdp'),
      rdpgw: i18n.t('views.direct-viewer.description.rdpgw')
    }

    const resetDesktop = (action) => {
      const token = context.root.$route.params.pathMatch
      $store.dispatch('updateResetModal', {
        show: true,
        item: { token: token, action: action }
      })
    }

    const isWaiting = computed(() => [desktopStates.waitingip].includes(directViewer.value.state.toLowerCase()))

    watch(isWaiting, (newVal, prevVal) => {
      if (newVal === false && directViewer.value.viewers.length === 1 && directViewer.value.viewers[0].protocol === 'rdp') {
        $store.dispatch('openDirectViewerDesktop', directViewer.value.viewers[0])
      }
    })

    window.onload = () => {
      const token = context.root.$route.params.pathMatch
      $store.dispatch('getDirectViewers', { token }).then(() => {
        if (directViewer.value.viewers.length === 1 && directViewer.value.viewers[0].kind === 'browser' && (directViewer.value.viewers[0].protocol === 'vnc' || (directViewer.value.viewers[0].protocol === 'rdp' && !isWaiting.value))) {
          $store.dispatch('openDirectViewerDesktop', directViewer.value.viewers[0])
        }
        $store.dispatch('openSocket', { jwt: directViewer.value.jwt, room: directViewer.value.desktopId })
        localStorage.viewerToken = directViewer.value.jwt
      })
    }

    window.onunload = () => {
      $store.dispatch('closeSocket')
    }

    return {
      loading,
      directViewer,
      browserViewers,
      fileViewers,
      viewerDescription,
      resetDesktop,
      status
    }
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

.column-header {
  height: 75px;
}

#powered-by {
  margin: 2rem;
}

#powered-by a {
  color: inherit !important;
  text-decoration: none !important;
}

</style>
