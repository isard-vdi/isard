<template>
          <b-card
            :img-src= "require(`../assets/img/cards/${imageId}.jpg`)"
            class='border-0 mx-3 pb-2'
            img-alt='' img-top no-body
          >
            <!-- Info -->
            <b-icon
              icon='info-circle-fill'
              class='info-icon position-absolute cursor-pointer'
              :id="`card-info-icon-${desktop.id}`"
            ></b-icon>
            <b-tooltip :target="`card-info-icon-${desktop.id}`" :title="desktop.description"></b-tooltip>
            <!-- Desktop state -->
            <div class='machine-state px-4 d-flex flex-row align-content-center' :class="stateBarCssClass">
              <b-spinner v-if="desktopState === 'waitingip'" small variant='light' class='align-self-center mr-2'></b-spinner>
              <p class='mb-0 py-1' :class="{ 'text-white': !desktopState === 'stopped' }"> {{ desktop.type === 'nonpersistent' && desktopState === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${desktopState}.text`)}}</p>
            </div>

            <div class='p-2 h-100 d-flex flex-wrap flex-column'>
              <div class='mb-2 flex-grow-1'>
                <!-- Title -->
                <div class='font-weight-bold card-title' :id="`card-title-text-${desktop.id}`">{{ getCardTitle | truncate(20) }}</div>
                <b-tooltip :target="`card-title-text-${desktop.id}`" :title="getCardTitle"></b-tooltip>

                <!-- IP -->
                <p class='w-100 mb-0 card-text'>{{ desktop.ip ? `IP:  ${desktop.ip}` : '' }}</p>

                <!-- DESCRIPTION -->
                <p class='w-100 mb-0 card-text' :id="`card-description-text-${desktop.id}`">{{ !desktop.ip ? getCardDescription  : '' | truncate(30)}}</p>
                <b-tooltip :target="`card-description-text-${desktop.id}`" :title="getCardDescription"></b-tooltip>

                <!-- Template -->
                <p class='w-100 mb-0 card-text'
                  v-if="desktop.type === 'persistent' && template"
                  :id="`card-template-text-${desktop.id}`">
                  Plantilla: {{ template.name  | truncate(16) }}
                </p>
                <b-tooltip v-if="desktop.type === 'persistent' && template" :target="`card-template-text-${desktop.id}`" :title="template.name"></b-tooltip>
              </div>

              <!-- Actions -->
              <div class='d-flex flex-row mb-2 justify-content-between buttons-padding'>
                  <isard-button
                    v-if="!hideViewers && desktop.viewers && desktop.viewers.length === 1"
                    :viewerName="desktop.viewers[0]"
                    variant="primary"
                    :spinnerActive="waitingIp"
                    @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0]})">
                  </isard-button>
                  <isard-dropdown
                    v-else-if="!hideViewers"
                    :ddDisabled="!showDropDown"
                    cssClass='viewers-dropdown m-0'
                    variant='light'
                    :viewers="desktop.viewers && desktop.viewers.filter(item => item !== viewers[desktop.id])"
                    :desktop="desktop"
                    :viewerText="viewers[desktop.id] !== undefined ? getViewerText.substring(0, 13) : $t('views.select-template.viewers')"
                    :fullViewerText="viewers[desktop.id] !== undefined ? getViewerText : $t('views.select-template.viewers')"
                    :defaultViewer="viewers[desktop.id]"
                    :waitingIp="waitingIp"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>

                  <DesktopButton v-if="!desktop.state || (desktop.type === 'nonpersistent' && !['started', 'waitingip', 'stopped'].includes(desktopState))"
                    class="dropdown-text"
                    @buttonClicked="chooseDesktop(desktop.id)"
                    :buttColor = "buttCssColor"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.status.notCreated.action')">
                </DesktopButton>
                <DesktopButton v-if="desktop.type === 'persistent' || (desktop.type === 'nonpersistent' && desktop.state === 'Stopped' )"
                    class="dropdown-text"
                    @buttonClicked="changeDesktopStatus({ action: status[desktopState || 'stopped'].action, desktopId: desktop.id })"
                    :buttColor = "buttCssColor"
                    :spinnerActive ="false"
                    :buttText = "$t(`views.select-template.status.${desktopState}.action`)">
                </DesktopButton>
                <DesktopButton v-if="(desktop.state && desktop.type === 'nonpersistent' && ['started', 'waitingip', 'stopped'].includes(desktopState))"
                    class="dropdown-text"
                    @buttonClicked="deleteDesktop(desktop.id)"
                    buttColor = "btn-red"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.remove')">
                </DesktopButton>
              </div>
            </div>
          </b-card>
</template>

<script>
import i18n from '@/i18n'
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
    },
    hash (string) {
      const H = 48
      let total = 0

      for (var i = 0; i < string.length; i++) {
        total += total + string.charCodeAt(i)
      }

      return total % H + 1
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
        failed: 'state-failed'
      }
      return states[this.desktopState]
    },
    buttCssColor () {
      const stateColors = {
        stopped: 'btn-green',
        started: 'btn-red',
        waitingip: 'btn-orange',
        error: 'btn-red'
      }
      return stateColors[this.desktopState]
    },
    desktopState () {
      return (this.desktop.state && this.desktop.state.toLowerCase()) || 'stopped'
    },
    imageId () {
      return this.desktop.state && this.desktop.type === 'nonpersistent' && ['started', 'waitingip', 'stopped'].includes(this.desktopState) ? this.hash(this.template.id) : this.desktop.id && this.hash(this.desktop.id)
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
  data () {
    return {
      desktopStates,
      status,
      item: {}
    }
  }
}
</script>
