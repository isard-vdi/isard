<template>
          <b-card
            :img-src= "require(`../assets/img/cards/${imageId}.jpg`)"
            class='border-0 mx-3'
            img-alt='' img-top no-body
          >
            <!-- Info -->
            <b-icon
              icon='info-circle-fill'
              class='info-icon position-absolute cursor-pointer'
              v-b-tooltip="{ title: `${desktop.description ? desktop.description : $t(`components.desktop-cards.no-info-default`)}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
            ></b-icon>
            <!-- Desktop state -->
            <div class='machine-state px-4 d-flex flex-row align-content-center' :class="stateBarCssClass">
              <b-spinner v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(desktopState.toLowerCase())" small variant='light' class='align-self-center mr-2'></b-spinner>
              <p class='mb-0 py-1' :class="{ 'text-white': !desktopState === desktopStates.stopped }"> {{ desktop.type === 'nonpersistent' && desktopState === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${desktopState}.text`)}}</p>
            </div>

            <div class='p-2 h-100 d-flex flex-wrap flex-column' :class="{'startedHighlight': desktopState === desktopStates.started}">
              <div class='mb-2 flex-grow-1'>
                <!-- Title -->
                <div
                  class='font-weight-bold card-title'
                  v-b-tooltip="{ title: `${getCardTitle}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                    {{ getCardTitle | truncate(20) }}
                </div>

                <!-- IP -->
                <p class='w-100 mb-0 card-text'>{{ desktop.ip ? `IP:  ${desktop.ip}` : '' }}</p>

                <!-- DESCRIPTION -->
                <p class='w-100 mb-0 card-text' v-b-tooltip="{ title: `${getCardDescription}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                  {{ !desktop.ip ? getCardDescription  : '' | truncate(30)}}
                </p>

                <!-- Template -->
                <p class='w-100 mb-0 card-text'
                  v-if="desktop.type === 'persistent' && template"
                  v-b-tooltip="{ title: `${template.name}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                  Plantilla: {{ template.name  | truncate(16) }}
                </p>
              </div>

              <!-- Actions -->
              <div class='d-flex flex-row mb-2 justify-content-between buttons-padding'>
                <DesktopButton v-if="!desktop.state || (desktop.type === 'nonpersistent' && ![desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(desktopState))"
                    class="dropdown-text card-button"
                    :active="true"
                    @buttonClicked="chooseDesktop(desktop.id)"
                    :buttColor = "buttCssColor"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.status.notCreated.action')">
                </DesktopButton>
                <DesktopButton v-if="desktop.type === 'persistent' || (desktop.type === 'nonpersistent' && desktop.state && desktopState ===  desktopStates.stopped )"
                    class="dropdown-text card-button"
                    :active="![desktopStates.failed, desktopStates.working, desktopStates['shutting-down']].includes(desktopState.toLowerCase())"
                    @buttonClicked="changeDesktopStatus({ action: status[desktopState || 'stopped'].action, desktopId: desktop.id })"
                    :buttColor = "buttCssColor"
                    :spinnerActive ="false"
                    :buttText = "$t(`views.select-template.status.${desktopState}.action`)">
                </DesktopButton>
                <DesktopButton v-if="(desktop.state && desktop.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(desktopState))"
                    class="dropdown-text card-button"
                    :active="true"
                    @buttonClicked="deleteDesktop(desktop.id)"
                    buttColor = "btn-red"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.remove')">
                </DesktopButton>

                  <DesktopButton
                    v-if="!hideViewers && desktop.viewers && desktop.viewers.length === 1"
                    :active="desktopState === desktopStates.started"
                    :buttColor = "buttViewerCssColor"
                    :buttText="desktop.viewers[0]"
                    variant="primary"
                    :spinnerActive="waitingIp"
                    @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0]})">
                  </DesktopButton>
                  <isard-dropdown
                  v-if="desktop.type === 'persistent' || (desktop.type === 'nonpersistent' && desktop.state && [desktopStates.started, desktopStates.waitingip].includes(desktopState))"
                    :ddDisabled="!showDropDown"
                    cssClass='viewers-dropdown m-0'
                    :class="{ 'dropdown-inactive': !showDropDown }"
                    variant='light'
                    :viewers="desktop.viewers && desktop.viewers.filter(item => item !== viewers[desktop.id])"
                    :desktop="desktop"
                    :viewerText="viewers[desktop.id] !== undefined ? getViewerText.substring(0, 13) : $t('views.select-template.viewers')"
                    :fullViewerText="viewers[desktop.id] !== undefined ? getViewerText : $t('views.select-template.viewers')"
                    defaultViewer="browser"
                    :waitingIp="waitingIp"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>
              </div>
            </div>
          </b-card>
</template>

<script>
import i18n from '@/i18n'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { mapActions } from 'vuex'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { desktopStates, status } from '@/shared/constants'

export default {
  components: { DesktopButton, IsardDropdown },
  props: {
    desktop: Object,
    templates: {
      required: true,
      type: Array
    }
  },
  methods: {
    ...mapActions([
      'deleteDesktop',
      'openDesktop',
      'changeDesktopStatus'
    ]),
    chooseDesktop (template) {
      const data = new FormData()
      data.append('template', template)
      this.$store.dispatch('createDesktop', data)
    }
  },
  computed: {
    viewers () {
      return this.$store.getters.getViewers
    },
    stateBarCssClass () {
      const states = {
        stopped: 'state-off',
        started: 'state-on',
        waitingip: 'state-loading',
        error: 'state-error',
        failed: 'state-failed',
        working: 'state-loading',
        'shutting-down': 'state-loading'
      }
      return states[this.desktopState]
    },
    buttCssColor () {
      const stateColors = {
        stopped: 'btn-green',
        started: 'btn-red',
        waitingip: 'btn-red',
        error: 'btn-red'
      }
      return stateColors[this.desktopState]
    },
    buttViewerCssColor () {
      const stateColors = {
        stopped: 'btn-gray',
        started: 'btn-green',
        waitingip: 'btn-orange',
        error: 'btn-red'
      }
      return stateColors[this.desktopState]
    },
    desktopState () {
      return (this.desktop.state && this.desktop.state.toLowerCase()) || desktopStates.stopped
    },
    imageId () {
      return this.desktop.state && this.desktop.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip].includes(this.desktopState) ? DesktopUtils.hash(this.template.id) : this.desktop.id && DesktopUtils.hash(this.desktop.id)
    },
    waitingIp () {
      return this.desktopState === desktopStates.waitingip
    },
    showDropDown () {
      return [desktopStates.started, desktopStates.waitingip].includes(this.desktopState)
    },
    getViewerText () {
      const name = i18n.t(`views.select-template.viewer-name.${this.viewers[this.desktop.id]}`)
      return i18n.t('views.select-template.viewer', i18n.locale, { name: name })
    },
    hideViewers () {
      return this.desktop.state && this.desktop.type === 'nonpersistent' && this.desktopState === desktopStates.stopped
    },
    template () {
      return (this.desktop.template && this.templates.filter(template => template.id === this.desktop.template)[0]) || null
    },
    getCardTitle () {
      return this.desktop.type === 'persistent' || (!this.desktop.state && this.desktop.type === 'nonpersistent' && this.desktopState === desktopStates.stopped) ? this.desktop.name : this.template && this.template.name
    },
    getCardDescription () {
      return (this.desktop.description !== null && this.desktop.description !== undefined) ? this.desktop.description : ''
    }
  },
  watch: {
    desktopState: {
      immediate: true,
      handler: function (newState) {
        // if ([desktopStates.started, desktopStates.waitingip].includes(this.desktopState)) {
        //   this.highlightDropdown = true
        // }

        if ([desktopStates.started, desktopStates.waitingip].includes(this.desktopState)) {
          if (this.desktop) {
            this.$store.dispatch('setDefaultViewer', { id: this.desktop.id, viewer: 'browser' })
          }
        }
      }
    }
  },
  data () {
    return {
      desktopStates,
      status,
      item: {},
      highlightDropdown: false
    }
  }
}
</script>
