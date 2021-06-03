<template>
  <b-card class="shadow temporal_desktop m-3" no-body>
            <b-card-body>
              <b-row no-gutters>
                <b-col cols="4">
                  <font-awesome-icon class="mt-2" size="4x" :icon="desktop.icon" />
                </b-col>
                <b-col cols="8">
                  <b-card-title class="card-title">
                      <b-icon v-if="desktop.description" v-b-tooltip.hover :title="desktop.description" icon="info-circle" class="mr-1"></b-icon>
                      {{desktop.state ? templates.filter(template => template.id ===  desktop.template)[0].name : desktop.name}}
                  </b-card-title>
                  <b-card-sub-title class="card-sub-title mb-2" v-if="desktop.state">
                    <span>
                      <b-spinner v-if="waitingIp (desktop.state)" small/>
                      {{$t(`views.select-template.status.${desktop.state.toLowerCase()}.text`)}}
                    </span>
                    <p v-if="desktop.ip">IP: {{ desktop.ip }}</p>
                  </b-card-sub-title>
                  <!-- If the desktop doesn't exist we can create it using its template id -->
                  <b-button
                    v-if="!desktop.state" size="sm"
                    :variant="status.notCreated.variant"
                    @click="chooseDesktop(desktop.id)">
                      <font-awesome-icon :icon="status.notCreated.icon" class="mr-2"/>
                      {{$t('views.select-template.status.notCreated.action')}}
                  </b-button>
                  <span v-else>
                    <!-- If it's stopped we can start it -->
                    <b-button v-if="desktop.state.toLowerCase() === desktopStates.stopped" size="sm" :variant="status.stopped.variant"
                      @click="changeDesktopStatus({ action: status.stopped.action, desktopId: desktop.id })">
                        <font-awesome-icon :icon="status.stopped.icon" class="mr-2"/>
                        {{$t('views.select-template.status.stopped.action')}}
                    </b-button>
                    <!-- If it's executing we can use its viewers -->
                    <span v-else-if="showDropDown(desktop.state)">
                      <isard-button
                        v-if="desktop.viewers.length === 1"
                        variant="primary"
                        buttonSize="sm"
                        :viewerName="desktop.viewers[0]"
                        :spinnerActive="waitingIp(desktop.state)"
                        @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0], template: desktop.template})">
                      </isard-button>
                      <isard-dropdown
                        v-else
                        variant="primary"
                        cssClass="m-1"
                        labelSize="sm"
                        :viewers="desktop.viewers.filter(item => item !== viewers[desktop.template])"
                        :desktop="desktop"
                        :viewerText="viewers[desktop.template] !== undefined ? getViewerText(viewers[desktop.template]) : $t('views.select-template.viewers')"
                        :defaultViewer="viewers[desktop.template]"
                        :template="desktop.template"
                        :waitingIp="waitingIp(desktop.state)"
                        @dropdownClicked="openDesktop">
                      </isard-dropdown>
                    </span>
                    <!-- We can remove it anyways -->
                    <b-button variant="danger" size="sm" @click="deleteDesktop(desktop.id)" class="m-1">
                      <font-awesome-icon :icon="['fas', 'trash']" class="mr-2"/>
                      {{ $t('views.select-template.remove') }}
                    </b-button>
                  </span>
                </b-col>
              </b-row>
            </b-card-body>
          </b-card>
</template>

<script>
import i18n from '@/i18n'
import { mapActions } from 'vuex'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import IsardButton from '@/components/shared/IsardButton.vue'
import { desktopStates, status } from '@/shared/constants'

export default {
  components: { IsardDropdown, IsardButton },
  props: {
    desktop: {
      required: true,
      type: Object
    },
    templates: {
      required: true,
      type: Array
    }
  },
  methods: {
    ...mapActions([
      'openDesktop',
      'changeDesktopStatus'
    ]),
    waitingIp (desktopState) {
      return desktopState && desktopState.toLowerCase() === desktopStates.waitingip
    },
    showDropDown (state) {
      return state && [desktopStates.started, desktopStates.waitingip].includes(state.toLowerCase())
    },
    getViewerText (viewer) {
      const name = i18n.t(`views.select-template.viewer-name.${viewer}`)
      return i18n.t('views.select-template.viewer', i18n.locale, { name: name })
    }
  },
  computed: {
    viewers () {
      return this.$store.getters.getViewers
    }
  },
  data () {
    return {
      desktopStates,
      status
    }
  }
}
</script>

<style scoped>

  .temporal_desktop {
    min-height:100px !important;
    min-width:400px !important;
    z-index: 0 !important;
  }

  .card:hover{
    z-index: 1 !important;
    box-shadow: 8px 8px 5px blue;
    background-color: #eaf1ed;
  }

  .card-title {
    font-size: 0.9em;
    font-weight: bolder;
  }

  .card-sub-title {
    font-size: 0.8em;
  }

  .card-footer {
    font-size: 0.8em;
  }
</style>
