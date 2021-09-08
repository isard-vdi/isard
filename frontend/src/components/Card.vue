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

            <div class='p-2 h-100 d-flex flex-wrap flex-column' :class="{'startedHighlight': desktopState === desktopStates.started}">
              <div class='flex-grow-1'>

                <!-- Title -->
                <div class='font-weight-bold card-title ml-2 mt-2 mb-2'
                  v-b-tooltip="{ title: `${getCardTitle.length > MAX_TITLE_SIZE ? getCardTitle : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                    {{ getCardTitle | truncate(MAX_TITLE_SIZE) }}
                </div>

                <!-- DESCRIPTION -->
                <p class='w-100 mb-0 card-text ml-2 mb-2' v-b-tooltip="{ title: `${getCardDescription.length > MAX_DESCRIPTION_SIZE ? getCardDescription : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                  {{ getCardDescription | truncate(MAX_DESCRIPTION_SIZE)}}
                </p>

                <!-- State -->
                <div class='ml-4 d-flex flex-row justify-left'>
                  <b-spinner v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(desktopState.toLowerCase())" small variant='light' class='align-self-center mr-2 status-spinner'></b-spinner>
                  <p class='mb-0 text-state font-weight-bold' :class="statusTextCssColor"> {{ desktop.type === 'nonpersistent' && desktopState === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${desktopState}.text`)}}</p>
                </div>

                <!-- Actions -->
                <div class='d-flex flex-row justify-content-start ml-3 mb-1'>
                  <DesktopButton v-if="!desktop.state || (desktop.type === 'nonpersistent' && ![desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(desktopState))"
                      class="card-button"
                      :active="true"
                      @buttonClicked="chooseDesktop(desktop.id)"
                      :buttColor = "buttCssColor"
                      :spinnerActive ="false"
                      :buttText = "$t('views.select-template.status.notCreated.action')"
                      :iconName = "desktop.buttonIconName">
                  </DesktopButton>
                  <DesktopButton v-if="desktop.type === 'persistent' || (desktop.type === 'nonpersistent' && desktop.state && desktopState ===  desktopStates.stopped )"
                      class="card-button"
                      :active="![desktopStates.working, desktopStates['shutting-down']].includes(desktopState.toLowerCase())"
                      @buttonClicked="changeDesktopStatus({ action: status[desktopState || 'stopped'].action, desktopId: desktop.id })"
                      :buttColor = "buttCssColor"
                      :spinnerActive ="false"
                      :buttText = "$t(`views.select-template.status.${desktopState}.action`)"
                      :iconName = "desktop.buttonIconName">
                  </DesktopButton>
                  <DesktopButton v-if="(desktop.state && desktop.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(desktopState))"
                      class="card-button"
                      :active="true"
                      @buttonClicked="deleteDesktop(desktop.id)"
                      buttColor = "btn-red"
                      :spinnerActive ="false"
                      :buttText = "$t('views.select-template.remove')"
                      iconName = "trash">
                  </DesktopButton>
                </div>

                <!-- IP -->
                <p class='w-100 mb-0 card-text ml-2 mt-2 mb-1'>{{ desktop.ip ? `IP:  ${desktop.ip}` : '' }}</p>

                <!-- Template -->
                <p class='w-100 mb-0 card-text ml-2'
                  v-if="desktop.type === 'persistent' && template"
                  v-b-tooltip="{ title: `${template.name.length > MAX_TEMPLATE_TEXT_SIZE ? template.name : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }">
                  Plantilla: {{ template.name  | truncate(MAX_TEMPLATE_TEXT_SIZE) }}
                </p>
              </div>

              <!-- Actions -->
              <div v-if="[desktopStates.started, desktopStates.waitingip].includes(desktopState)" class='d-flex flex-column mb-2 buttons-padding buttons-margin'>
                <div class="ml-1 mb-1">{{ $t("components.desktop-cards.open-with") }}:</div>
                <div>
                  <DesktopButton
                    v-if="!hideViewers && desktop.viewers && desktop.viewers.length === 1"
                    :active="desktopState === desktopStates.started || (desktopState === desktopStates.waitingip && !singleViewerNeedsIp)"
                    :buttColor = "buttViewerCssColor"
                    :buttText="desktop.viewers[0]"
                    variant="primary"
                    :spinnerActive="waitingIp"
                    @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0]})">
                  </DesktopButton>
                  <isard-dropdown
                  v-if="!hideViewers && desktop.viewers && desktop.viewers.length > 1"
                    :ddDisabled="!showDropDown"
                    cssClass='viewers-dropdown m-0'
                    :class="{ 'dropdown-inactive': !showDropDown, 'dropdown-wait': isWaiting(getDefaultViewer), 'dropdown-active': !isWaiting(getDefaultViewer) }"
                    variant='light'
                    :viewers="filterViewerFromList"
                    :desktop="desktop"
                    :viewerText="getViewerText.substring(0, MAX_VIEWER_TEXT_SIZE)"
                    :fullViewerText="getViewerText"
                    :defaultViewer="getDefaultViewer"
                    :waitingIp="waitingIp"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>
                  </div>
              </div>
            </div>
          </b-card>
</template>

<script>
import i18n from '@/i18n'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { mapActions, mapGetters } from 'vuex'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { desktopStates, status } from '@/shared/constants'

const MAX_TITLE_SIZE = 20
const MAX_DESCRIPTION_SIZE = 30
const MAX_TEMPLATE_TEXT_SIZE = 16
const MAX_VIEWER_TEXT_SIZE = 40

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
      'changeDesktopStatus',
      'createDesktop'
    ]),
    chooseDesktop (template) {
      const data = new FormData()
      data.append('template', template)
      this.createDesktop(data)
    },
    isWaiting (viewer) {
      return this.getDefaultViewer && (this.waitingIp && DesktopUtils.viewerNeedsIp(viewer))
    }
  },
  computed: {
    ...mapGetters(['getViewers']),
    filterViewerFromList () {
      return DesktopUtils.filterViewerFromList(this.desktop.viewers, this.getDefaultViewer)
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
        failed: 'btn-red'
      }
      return stateColors[this.desktopState]
    },
    buttViewerCssColor () {
      const stateColors = {
        stopped: 'btn-gray',
        started: 'btn-green',
        waitingip: 'btn-orange',
        failed: 'btn-red'
      }
      return stateColors[this.desktopState]
    },
    statusTextCssColor () {
      if (this.desktop.type === 'nonpersistent' && this.desktopState === desktopStates.stopped) {
        return 'status-green'
      }

      const stateColors = {
        stopped: 'status-gray',
        started: 'status-green',
        waitingip: 'status-orange',
        failed: 'status-red',
        'shutting-down': 'status-orange',
        working: 'status-orange'
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
      const name = this.getDefaultViewer !== '' ? i18n.t(`views.select-template.viewer-name.${this.getDefaultViewer}`) : i18n.t('views.select-template.viewers')
      return this.getDefaultViewer !== '' ? i18n.t('views.select-template.viewer', i18n.locale, { name: name }) : name
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
    },
    getDefaultViewer () {
      if (this.desktop.viewers !== undefined) {
        if (this.getViewers[this.desktop.id] !== undefined && this.desktop.viewers.includes(this.getViewers[this.desktop.id])) {
          return this.getViewers[this.desktop.id]
        } else if (this.desktop.viewers.length > 0) {
          return this.desktop.viewers.includes('browser') ? 'browser' : this.desktop.viewers[0]
        }
      }
      return ''
    },
    singleViewerNeedsIp () {
      if (!this.desktop.viewers || !this.desktop.viewers.length > 0) {
        return false
      }
      return DesktopUtils.viewerNeedsIp(this.desktop.viewers[0])
    }
  },
  data () {
    return {
      desktopStates,
      status,
      item: {},
      highlightDropdown: false,
      MAX_TITLE_SIZE,
      MAX_DESCRIPTION_SIZE,
      MAX_TEMPLATE_TEXT_SIZE,
      MAX_VIEWER_TEXT_SIZE
    }
  }
}
</script>
