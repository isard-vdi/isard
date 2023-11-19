<template>
  <b-overlay
    :show="show"
    rounded="lg"
  >
    <b-card
      :img-src="`..${desktop.image.url}`"
      class="border-0 mx-3"
      :aria-hidden="show ? 'true' : null"
      img-alt=""
      img-top
      no-body
    >
      <vue-fab
        v-if="desktop.editable && desktop.type === 'persistent'"
        icon="more_vert"
        main-btn-color="#bcc6cc"
        class="info-icon position-absolute"
        size="small"
        unfold-direction="down"
        :scroll-auto-hide="false"
      >
        <fab-item
          v-if="desktop.editable && desktop.needsBooking && !desktop.tag"
          v-b-tooltip="{ title: `${$t('components.desktop-cards.actions.booking')}`,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          :idx="getUser.role_id != 'user' ? 4 : 2"
          icon="event"
          color="#eead47"
          @clickItem="onClickBookingDesktop(desktop)"
        />
        <fab-item
          v-if="getUser.role_id != 'user'"
          v-b-tooltip="{ title: `${$t('components.desktop-cards.actions.direct-link')}`,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          :idx="3"
          icon="link"
          color="#ab3ed1"
          @clickItem="onClickOpenDirectViewerModal({itemId: desktop.id})"
        />
        <fab-item
          v-if="getUser.role_id != 'user' && desktop.type === 'persistent'"
          v-b-tooltip="{ title: `${$t('components.desktop-cards.actions.template')}`,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          :idx="2"
          color="#97c277"
          @clickItem="onClickGoToNewTemplate(desktop.id)"
        >
          <font-awesome-icon
            :icon="['fas', 'cubes']"
            class="ml-1 mt-1 text-white"
          />
        </fab-item>
        <fab-item
          v-if="desktop.type === 'persistent'"
          v-b-tooltip="{ title: `${$t('components.desktop-cards.actions.delete')}`,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          :idx="1"
          icon="delete"
          color="#e34934"
          @clickItem="onClickDeleteDesktop"
        />
        <fab-item
          v-b-tooltip="{ title: `${$t('components.desktop-cards.actions.edit')}`,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          :idx="0"
          icon="edit"
          color="#318bb5"
          @clickItem="onClickGoToEditDesktop({itemId: desktop.id, returnPage: currentRouteName})"
        />
      </vue-fab>

      <!-- Desktop next booking -->
      <div
        v-if="desktop.needsBooking"
        class="machine-notification-bar px-3 d-flex flex-row align-content-center text-white notification-bar"
        :class="notificationBarCssClass"
      >
        <p
          v-b-tooltip.hover="{ title: `${getBookingNotificationBar(desktop.nextBookingStart, desktop.nextBookingEnd).length > MAX_BOOKING_TEXT_SIZE ? getBookingNotificationBar(desktop.nextBookingStart, desktop.nextBookingEnd) : '' }` , placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
          class="mb-0 py-2 text-white text-truncate"
          :title="`${getBookingNotificationBar(desktop.nextBookingStart, desktop.nextBookingEnd).length > MAX_BOOKING_TEXT_SIZE ? getBookingNotificationBar(desktop.nextBookingStart, desktop.nextBookingEnd) : '' }`"
        >
          {{ getBookingNotificationBar(desktop.nextBookingStart, desktop.nextBookingEnd) }}
        </p>
      </div>
      <!-- Desktop next booking -->
      <div
        v-else-if="desktop.shutdown"
        class="machine-notification-bar px-4 d-flex flex-row align-content-center text-white bg-dark notification-bar"
      >
        <p class="mb-0 py-2 text-white">
          {{ desktop.shutdown }}
        </p>
      </div>

      <div
        class="p-2 h-100 d-flex flex-wrap flex-column"
        :class="`${desktop.needsBooking || desktop.shutdown ? 'notification-bar' : '' } getCardBackgroundColor` "
      >
        <div class="flex-grow-1">
          <!-- Title -->
          <div
            v-b-tooltip="{ title: `${getCardTitle.length > MAX_TITLE_SIZE ? getCardTitle : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
            class="font-weight-bold card-title ml-2 mt-2 mb-2"
          >
            {{ getCardTitle | truncate(MAX_TITLE_SIZE) }}
          </div>

          <!-- DESCRIPTION -->
          <p
            v-b-tooltip="{ title: `${getCardDescription.length > MAX_DESCRIPTION_SIZE ? getCardDescription : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
            class="w-100 mb-0 card-text ml-2 mb-2"
          >
            {{ getCardDescription | truncate(MAX_DESCRIPTION_SIZE) }}
          </p>

          <!-- State -->
          <div class="ml-4 d-flex flex-row justify-left">
            <b-spinner
              v-if="[desktopStates.downloading, desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(desktopState.toLowerCase())"
              small
              variant="light"
              class="align-self-center mr-2 status-spinner"
            />
            <p
              class="mb-0 text-state font-weight-bold"
              :class="statusTextCssColor"
            >
              {{ desktop.type === 'nonpersistent' && desktopState === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${desktopState}.text`) }}
            </p>
          </div>

          <div
            v-if="desktop.progress"
            class="ml-4 mr-4 flex-row justify-left"
          >
            <small>{{ desktop.progress.size }} - {{ desktop.progress.throughput_average }}/s - {{ desktop.progress.time_left }}</small>
            <b-progress
              :max="100"
              height="2rem"
            >
              <b-progress-bar
                variant="secondary"
                :value="desktop.progress.percentage"
                show-progress
                animated
              >
                <strong>{{ desktop.progress.percentage }} %</strong>
              </b-progress-bar>
            </b-progress>
          </div>

          <!-- Actions -->
          <div
            v-if="[desktopStates.started, desktopStates.waitingip, desktopStates.stopped, desktopStates.failed, desktopStates['shutting-down'], desktopStates.paused].includes(desktopState)"
            class="d-flex flex-row justify-content-start ml-3 mb-1"
          >
            <!-- Main action button nonpersistent -->
            <DesktopButton
              v-if="!desktop.state"
              class="card-button"
              :active="true"
              :button-class="buttCssColor"
              :spinner-active="false"
              :butt-text="$t('views.select-template.status.notCreated.action')"
              :icon-name="desktop.buttonIconName"
              @buttonClicked="chooseDesktop(desktop.id)"
            />
            <!-- Main action button persistent-->
            <DesktopButton
              v-else-if="desktop.type === 'persistent' || (desktop.type === 'nonpersistent' && desktop.state && desktopState === desktopStates.stopped )"
              class="card-button"
              :active="true"
              :button-class="buttCssColor"
              :spinner-active="false"
              :butt-text="$t(`views.select-template.status.${desktopState}.action`)"
              :icon-name="desktop.buttonIconName"
              @buttonClicked="changeDesktopStatus(desktop, { action: status[desktopState || 'stopped'].action, desktopId: desktop.id })"
            />
            <!-- Delete action button-->
            <DesktopButton
              v-if="desktop.state && desktop.type === 'nonpersistent'"
              class="card-button"
              :active="true"
              button-class="btn-red"
              :spinner-active="false"
              :butt-text="$t('views.select-template.remove')"
              icon-name="trash"
              @buttonClicked="deleteNonpersistentDesktop(desktop.id)"
            />
          </div>

          <!-- IP -->
          <p class="w-100 mb-0 card-text ml-2 mt-2 mb-1">
            {{ desktop.ip ? `IP:  ${desktop.ip}` : '' }}
          </p>

          <!-- Template -->
          <p
            v-if="desktop.type === 'persistent' && template"
            v-b-tooltip="{ title: `${template.name.length > MAX_TEMPLATE_TEXT_SIZE ? template.name : ''}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
            class="w-100 mb-0 card-text ml-2"
          >
            {{ $t('forms.new-desktop.desktop-template') }}: {{ template.name | truncate(MAX_TEMPLATE_TEXT_SIZE) }}
          </p>
        </div>

        <!-- Actions -->
        <div
          v-if="[desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(desktopState)"
          class="d-flex flex-column mb-2 buttons-padding buttons-margin"
        >
          <div class="ml-1 mb-1">
            {{ $t("components.desktop-cards.open-with") }}:
          </div>
          <div>
            <DesktopButton
              v-if="!hideViewers && desktop.viewers && desktop.viewers.length === 1"
              :active="desktopState === desktopStates.started || (desktopState === desktopStates.waitingip && !singleViewerNeedsIp)"
              :button-class="!singleViewerNeedsIp ? 'btn-green' : buttViewerCssColor"
              :butt-text="getViewerText"
              variant="primary"
              :spinner-active="waitingIp"
              @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0]})"
            />
            <isard-dropdown
              v-if="!hideViewers && desktop.viewers && desktop.viewers.length > 1"
              :dd-disabled="!showDropDown"
              css-class="viewers-dropdown m-0"
              :class="{ 'dropdown-inactive': !showDropDown, 'dropdown-wait': viewerNeedsIp(getDefaultViewer) && isWaiting(desktop.interfaces), 'dropdown-active': !viewerNeedsIp(getDefaultViewer) || !isWaiting(desktop.interfaces) }"
              variant="light"
              :viewers="filterViewerFromList"
              :desktop="desktop"
              :viewer-text="getViewerText.substring(0, MAX_VIEWER_TEXT_SIZE)"
              :full-viewer-text="getViewerText"
              :default-viewer="getDefaultViewer"
              :waiting-ip="waitingIp"
              @dropdownClicked="openDesktop"
            />
          </div>
        </div>
      </div>
    </b-card>
  </b-overlay>
</template>

<script>
import i18n from '@/i18n'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { ErrorUtils } from '@/utils/errorUtils'
import { mapActions, mapGetters } from 'vuex'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { desktopStates, status } from '@/shared/constants'
import { DateUtils } from '@/utils/dateUtils'

const MAX_TITLE_SIZE = 20
const MAX_DESCRIPTION_SIZE = 30
const MAX_TEMPLATE_TEXT_SIZE = 16
const MAX_VIEWER_TEXT_SIZE = 40
const MAX_BOOKING_TEXT_SIZE = 35

export default {
  components: { DesktopButton, IsardDropdown },
  props: {
    desktop: Object,
    templates: {
      required: true,
      type: Array
    }
  },
  setup (_, context) {
    const $store = context.root.$store

    const changeDesktopStatus = (desktop, data) => {
      if (canStart(desktop)) {
        $store.dispatch('changeDesktopStatus', data)
      } else {
        $store.dispatch('checkCanStart', { id: desktop.id, type: 'desktop', profile: desktop.reservables.vgpus[0], action: data.action })
      }
    }

    const canStart = (desktop) => {
      if (desktop.needsBooking) {
        return desktop.bookingId
      } else {
        return true
      }
    }

    const onClickBookingDesktop = (desktop) => {
      const data = { id: desktop.id, type: 'desktop', name: desktop.name }
      $store.dispatch('goToItemBooking', data)
    }

    return {
      changeDesktopStatus,
      onClickBookingDesktop
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
      MAX_VIEWER_TEXT_SIZE,
      MAX_BOOKING_TEXT_SIZE,
      show: false
    }
  },
  computed: {
    ...mapGetters(['getViewers', 'getCurrentTab', 'getUser']),
    filterViewerFromList () {
      return DesktopUtils.filterViewerFromList(this.desktop.viewers, this.getDefaultViewer)
    },
    notificationBarCssClass () {
      const states = {
        stopped: 'state-off',
        started: 'state-on',
        waitingip: 'state-loading',
        error: 'state-error',
        failed: 'state-failed',
        working: 'state-loading',
        'shutting-down': 'state-loading',
        booking: 'booking-notification'
      }
      return states[this.desktop.needsBooking ? 'booking' : this.desktopState]
    },
    buttCssColor () {
      const stateColors = {
        stopped: 'btn-green',
        'shutting-down': 'btn-red',
        started: 'btn-red',
        waitingip: 'btn-red',
        failed: 'btn-orange',
        paused: 'btn-red'
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
        working: 'status-orange',
        downloading: 'status-orange',
        paused: 'status-red'
      }
      return stateColors[this.desktopState]
    },
    getCardBackgroundColor () {
      if (this.desktop.server) {
        return 'serverHighlight'
      } else if (this.desktopState === desktopStates.started) {
        return 'startedHighlight'
      } else {
        return ''
      }
    },
    desktopState () {
      return (this.desktop.state && this.desktop.state.toLowerCase()) || desktopStates.stopped
    },
    waitingIp () {
      return this.desktopState === desktopStates.waitingip
    },
    showDropDown () {
      return [desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(this.desktopState)
    },
    getViewerText () {
      return this.getDefaultViewer !== '' ? i18n.t(`views.select-template.viewer-name.${this.getDefaultViewer}`) : i18n.t('views.select-template.viewers')
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
    },
    currentRouteName () {
      return this.$route.name
    }
  },
  destroyed () {
    this.$snotify.clear()
  },
  methods: {
    ...mapActions([
      'deleteDesktop',
      'deleteNonpersistentDesktop',
      'openDesktop',
      'createDesktop',
      'navigate',
      'goToEditDomain',
      'fetchDirectLink',
      'goToNewTemplate'
    ]),
    getBookingNotificationBar (dateStart, dateEnd) {
      if (DateUtils.dateIsAfter(dateEnd, new Date()) && DateUtils.dateIsBefore(dateStart, new Date())) {
        return i18n.t('components.desktop-cards.notification-bar.booking-ends') + DateUtils.formatAsTime(dateEnd) + ' ' + DateUtils.formatAsDayMonth(dateEnd)
      } else if (dateStart) {
        return i18n.t('components.desktop-cards.notification-bar.next-booking') + ': ' + DateUtils.formatAsTime(dateStart) + ' ' + DateUtils.formatAsDayMonth(dateStart)
      } else {
        return i18n.t('components.desktop-cards.notification-bar.no-next-booking')
      }
    },
    chooseDesktop (template) {
      this.$snotify.clear()

      const yesAction = () => {
        const data = new FormData()
        data.append('template', template)
        this.$snotify.clear()
        this.createDesktop(data)
      }

      const noAction = (toast) => {
        this.$snotify.clear()
      }

      this.$snotify.prompt(`${i18n.t('messages.confirmation.create-nonpersistent')}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    },
    isWaiting (interfaces) {
      return (this.waitingIp || this.desktopState === 'shutting-down') && DesktopUtils.networkNeedsIp(interfaces)
    },
    viewerNeedsIp (viewer) {
      return DesktopUtils.viewerNeedsIp(viewer)
    },
    onClickGoToNewTemplate (desktopId) {
      if (this.desktop.server) {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.new-template-server'), '', true, 2000)
      } else if (this.desktopState === desktopStates.stopped) {
        this.goToNewTemplate(desktopId)
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.new-template-stop'), '', true, 2000)
      }
    },
    onClickGoToEditDesktop (payload) {
      if (this.desktop.server && this.desktopState !== desktopStates.failed) {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.edit-desktop-server'), '', true, 2000)
      } else if ([desktopStates.failed, desktopStates.stopped].includes(this.desktopState)) {
        this.goToEditDomain(payload.itemId)
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.edit-desktop-stop'), '', true, 2000)
      }
    },
    onClickDeleteDesktop (toast) {
      if ([desktopStates.failed, desktopStates.stopped].includes(this.desktopState)) {
        this.$snotify.clear()

        const yesAction = () => {
          toast.valid = true // default value
          this.$snotify.remove(toast.id)
          this.deleteDesktop(this.desktop.id)
        }

        const noAction = (toast) => {
          this.$snotify.remove(toast.id) // default
        }

        this.$snotify.prompt(`${i18n.t('messages.confirmation.delete-desktop', { name: this.getCardTitle })}`, {
          position: 'centerTop',
          buttons: [
            { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
            { text: `${i18n.t('messages.no')}`, action: noAction }
          ],
          placeholder: ''
        })
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.delete-desktop-stop'), '', true, 2000)
      }
    },
    onClickOpenDirectViewerModal () {
      this.fetchDirectLink(this.desktop.id)
    }
  }
}
</script>
