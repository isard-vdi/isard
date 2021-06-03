<template>
  <b-card class="shadow persistent_desktop m-3 border-secondary" no-body>
              <b-card-body :class="desktop.template && templates.filter(template => template.id ===  desktop.template).length > 0 ? '' : 'mt-4'">
                <font-awesome-icon size="4x" :icon="desktop.icon" class="mb-2"/>
                <b-card-title class="card-title">
                    <b-icon v-if="desktop.description" v-b-tooltip.hover :title="desktop.description" icon="info-circle" class="mr-1"></b-icon>
                    {{ desktop.name }}
                </b-card-title>
                <b-card-sub-title class="mb-2 card-sub-title">
                    <span>
                      <b-spinner v-if="waitingIp (desktop.state)" small/>
                      {{$t(`views.select-template.status.${desktop.state.toLowerCase()}.text`)}}
                    </span>
                    <p v-if="desktop.ip">IP: {{ desktop.ip }}</p>
                </b-card-sub-title>
                <!-- Viewers button/dropdown -->
                <span v-if="showDropDown(desktop.state)">
                  <isard-button
                    v-if="desktop.viewers.length === 1"
                    :viewerName="desktop.viewers[0]"
                    variant="primary"
                    :spinnerActive="waitingIp(desktop.state)"
                    @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0]})">
                  </isard-button>
                  <isard-dropdown
                    v-else
                    variant="primary"
                    cssClass="m-1"
                    :viewers="desktop.viewers.filter(item => item !== viewers[desktop.id])"
                    :desktop="desktop"
                    :viewerText="viewers[desktop.id] !== undefined ? getViewerText(viewers[desktop.id]) : $t('views.select-template.viewers')"
                    :defaultViewer="viewers[desktop.id]"
                    :waitingIp="waitingIp (desktop.state)"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>
                </span>
                <!-- Change status button -->
                <b-button
                  v-if="['started','stopped','waitingip'].includes(desktop.state.toLowerCase())"
                  :variant="status[desktop.state.toLowerCase()].variant" class="m-1"
                  @click="changeDesktopStatus({ action: status[desktop.state.toLowerCase()].action, desktopId: desktop.id })">
                    <font-awesome-icon :icon="status[desktop.state.toLowerCase()].icon" class="mr-2"/>
                    {{$t(`views.select-template.status.${desktop.state.toLowerCase()}.action`)}}
                </b-button>
              </b-card-body>
            <b-card-footer class="card-footer" v-if="desktop.template && templates.filter(template => template.id ===  desktop.template).length > 0">
                <b>{{$t('views.select-template.template')}}:</b>
                {{templates.filter(template => template.id ===  desktop.template)[0].name}}
            </b-card-footer>
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
    desktop: Object,
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

  .persistent_desktop {
    min-height:250px !important;
    min-width:400px !important;
    z-index: 0 !important;
    transition: 0.3s;
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
