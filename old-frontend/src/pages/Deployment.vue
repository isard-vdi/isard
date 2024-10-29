<template>
  <b-container
    id="content"
    fluid
  >
    <span
      class="d-flex justify-content-between align-items-center"
    >
      <h5 class="font-weight-bold mb-0">
        <b-iconstack
          v-if="deployment.needsBooking"
          font-scale="1"
          role="button"
          :title="$t('components.desktop-cards.actions.booking')"
          @click="onClickBookingDesktop(deployment)"
        >
          <b-icon
            stacked
            icon="calendar"
            variant="warning"
          />
          <b-icon
            stacked
            icon="exclamation-triangle-fill"
            scale="0.5"
            shift-v="-1"
            variant="warning"
          />
        </b-iconstack>
        {{ deployment.name }}
        <b-badge
          v-if="deployment.needsBooking"
          class="ml-2"
          variant="warning"
        >
          {{ bookingBadge }}
        </b-badge>
      </h5>
      <p
        class="text-muted mb-0"
      >
        {{ desktopsBadge }} | {{ startedBadge }} | {{ visibleBadge }}
      </p>
    </span>
    <hr class="mb-0">
    <IsardTable
      :items="sortedDesktops"
      :loading="!(getDeploymentLoaded)"
      :default-per-page="perPage"
      :page-options="pageOptions"
      :filter-on="filterOn"
      :fields="fields.filter(field => field.visible !== false)"
      :row-class="rowClass"
      class="px-5 table-scrollable-div"
      style="height: calc(100vh - 200px) !important;"
    >
      <template #cell(image)="data">
        <!-- INFO -->
        <b-icon
          v-b-tooltip="{ title: `${data.item.description ? data.item.description : $t(`components.desktop-cards.no-info-default`)}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
          icon="info-circle-fill"
          class="info-icon position-absolute cursor-pointer"
        />
        <!-- IMAGE -->
        <b-avatar
          :src="data.item.userPhoto"
          referrerPolicy="no-referrer"
          size="60px"
        />
      </template>
      <template #cell(user)="data">
        <p class="m-0 font-weight-bold">
          {{ data.item.userName }}
        </p>
      </template>
      <template #cell(group)="data">
        <p class="text-dark-gray m-0">
          {{ data.item.groupName }}
        </p>
      </template>
      <template #cell(last)="data">
        <p class="text-dark-gray m-0">
          {{ getDate(data.item.last) }}
        </p>
      </template>
      <template #cell(ip)="data">
        <p class="text-dark-gray m-0">
          {{ data.item.ip }}
        </p>
      </template>
      <template #cell(state)="data">
        <div class="d-flex justify-content-center align-items-center">
          <!-- STATE DOT -->
          <div
            v-if="![desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down'], desktopStates.updating, desktopStates.not_created].includes(getItemState(data.item))"
            :class="'state-dot mr-2 ' + stateCssClass(getItemState(data.item))"
          />
          <!-- SPINNER -->
          <b-spinner
            v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down'], desktopStates.updating, desktopStates.creating].includes(getItemState(data.item))"
            small
            class="align-self-center mr-2 spinner-loading"
          />
          <!-- TITLE -->
          <p class="mb-0 text-medium-gray flex-grow">
            {{ $t(`views.select-template.status.${getItemState(data.item)}.text`) }}
          </p>
        </div>
      </template>
      <template #cell(viewers)="data">
        <div class="">
          <DesktopButton
            v-if="!hideViewers && data.item.viewers !== undefined && data.item.viewers.length === 1"
            :active="getItemState(data.item) === desktopStates.started"
            :button-class="buttViewerCssColor"
            :butt-text="data.item.viewers[0]"
            variant="primary"
            :spinner-active="waitingIp"
            @buttonClicked="openDesktop({desktopId: data.item.id, viewer: data.item.viewers && data.item.viewers[0]})"
          />
          <isard-dropdown
            v-else
            :dd-disabled="!showDropDown(data.item)"
            :class="{ 'dropdown-inactive': !showDropDown(data.item) }"
            css-class="viewers-dropdown flex-grow-1"
            variant="light"
            :viewers="data.item.viewers && data.item.viewers.filter(item => item !== getDefaultViewer(data.item))"
            :desktop="data.item"
            :viewer-text="getViewerText(data.item).substring(0, 40)"
            full-viewer-text=""
            :default-viewer="getDefaultViewer(data.item)"
            :waiting-ip="data.item.state && data.item.state.toLowerCase() === desktopStates.waitingip"
            @dropdownClicked="openDesktop"
          />
        </div>
      </template>
      <template #cell(action)="data">
        <!-- Main action button persistent -->
        <DesktopButton
          v-if="![desktopStates.working].includes(getItemState(data.item))"
          class="table-action-button"
          :active="canStart(data.item)"
          :button-class="canStart(data.item) ? buttCssColor(getItemState(data.item)) : ''"
          :spinner-active="false"
          :butt-text="$t(`views.select-template.status.${getItemState(data.item)}.action`)"
          :icon-name="data.item.buttonIconName"
          @buttonClicked="changeDesktopStatus({ action: status[getItemState(data.item) || 'stopped'].action, desktopId: data.item.id })"
        />
      </template>
      <template #cell(options)="data">
        <div class="d-flex align-items-center">
          <b-button
            class="rounded-circle btn-red px-2 mr-2"
            :title="$t('components.deployment-desktop-list.actions.delete')"
            @click="onClickDeleteDesktop(data.item)"
          >
            <b-icon
              icon="x"
              scale="1"
            />
          </b-button>
          <b-button
            :class="`rounded-circle ${data.item.visible ? 'btn-blue' : 'btn-grey' } px-2 mr-2`"
            :title="data.item.visible ? $t('components.deployment-desktop-list.actions.hide') : $t('components.deployment-desktop-list.actions.show')"
            @click="onClickDesktopVisible(data.item)"
          >
            <b-icon
              :icon="data.item.visible ? 'eye-fill' : 'eye-slash-fill'"
              scale="0.75"
            />
          </b-button>
        </div>
      </template>
    </IsardTable>
  </b-container>
</template>
<script>
// @ is an alias to /src
import IsardTable from '@/components/shared/IsardTable.vue'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { mapActions, mapGetters } from 'vuex'
import { desktopStates, status } from '@/shared/constants'
import { computed, ref, reactive } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { ErrorUtils } from '@/utils/errorUtils'
import i18n from '@/i18n'

export default {
  components: {
    IsardTable,
    DesktopButton,
    IsardDropdown
  },
  setup (props, context) {
    const $store = context.root.$store

    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const filterOn = reactive(['userName', 'groupName'])

    const rowClass = (item, type) => {
      if (item && type === 'row') {
        if (item.visible === true) {
          return 'cursor-pointer visibleHighlight'
        } else {
          return 'cursor-pointer'
        }
      } else {
        return null
      }
    }

    const deployment = computed(() => $store.getters.getDeployment)
    const badgeVariant = computed(() => deployment.value.visible ? 'success' : 'danger')

    const deploymentVariant = computed(() => deployment.value.visible ? 'visibleHighlight' : 'alert-danger')

    const badgeText = computed(() => deployment.value.visible ? i18n.t('views.deployment.visibility.visible') : i18n.t('views.deployment.visibility.not-visible'))

    const onClickBookingDesktop = (deployment) => {
      const data = { id: deployment.id, type: 'deployment', name: deployment.name }
      $store.dispatch('goToItemBooking', data)
    }

    const bookingBadge = computed(() => {
      if (DateUtils.dateIsAfter(deployment.value.nextBookingEnd, new Date()) && DateUtils.dateIsBefore(deployment.value.nextBookingStart, new Date())) {
        return i18n.t('components.desktop-cards.notification-bar.booking-ends') + DateUtils.formatAsTime(deployment.value.nextBookingEnd) + ' ' + DateUtils.formatAsDayMonth(deployment.value.nextBookingEnd)
      } else if (deployment.value.nextBookingStart) {
        return i18n.t('components.desktop-cards.notification-bar.next-booking') + ': ' + DateUtils.formatAsTime(deployment.value.nextBookingStart) + ' ' + DateUtils.formatAsDayMonth(deployment.value.nextBookingStart)
      } else {
        return i18n.t('components.desktop-cards.notification-bar.no-next-booking')
      }
    })

    const desktopsBadge = computed(() => {
      const desktopsCreating = deployment.value.desktops.filter(d => [desktopStates.creating].includes(d.state.toLowerCase())).length
      if (desktopsCreating !== 0) {
        return i18n.t('views.deployment.desktop.desktops-total-creating', {
          total: deployment.value.desktops.length,
          creating: desktopsCreating
        })
      } else {
        return i18n.t('views.deployment.desktop.desktops') + ': ' + deployment.value.desktops.length
      }
    })
    const startedBadge = computed(() => {
      return i18n.t('views.deployment.desktop.started') + ': ' + deployment.value.desktops.filter(d => [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase())).length
    })
    const visibleBadge = computed(() => {
      return i18n.t('views.deployment.desktop.visible') + ': ' + deployment.value.desktops.filter(d => d.visible).length
    })

    const getDate = (date) => {
      return DateUtils.dateAbsolute(date)
    }

    const canStart = (desktop) => {
      if (desktop.needsBooking) {
        return desktop.bookingId
      } else if ([desktopStates.creating].includes(desktop.state.toLowerCase())) {
        return false
      } else {
        return true
      }
    }

    const fields = [
      {
        key: 'image',
        sortable: false,
        label: '',
        thStyle: { width: '5%' },
        tdClass: 'image position-relative'
      },
      {
        key: 'user',
        sortable: true,
        label: `${i18n.t('components.deployment-desktop-list.table-header.user')}`,
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'group',
        sortable: true,
        label: `${i18n.t('components.deployment-desktop-list.table-header.group')}`,
        thStyle: { width: '30%' },
        tdClass: 'description'
      },
      {
        key: 'last',
        sortable: true,
        label: `${i18n.t('components.deployment-desktop-list.table-header.last')}`,
        thStyle: { width: '10%' },
        tdClass: 'last'
      },
      {
        key: 'ip',
        sortable: true,
        label: 'IP',
        thStyle: { width: '10%' },
        tdClass: 'ip'
      },
      {
        key: 'state',
        sortable: true,
        label: `${i18n.t('components.deployment-desktop-list.table-header.state')}`,
        thStyle: { width: '10%' },
        tdClass: 'state'
      },
      {
        key: 'viewers',
        thStyle: { width: '15%' },
        label: `${i18n.t('components.deployment-desktop-list.table-header.viewers')}`,
        tdClass: 'viewers'
      },
      {
        key: 'action',
        label: `${i18n.t('components.deployment-desktop-list.table-header.action')}`,
        thStyle: { width: '10%' },
        tdClass: 'px-4 action'
      },
      {
        key: 'options',
        label: '',
        thStyle: { width: '5%' }
      }
    ]

    return {
      deployment,
      badgeVariant,
      badgeText,
      deploymentVariant,
      onClickBookingDesktop,
      bookingBadge,
      desktopsBadge,
      startedBadge,
      visibleBadge,
      perPage,
      pageOptions,
      filterOn,
      rowClass,
      getDate,
      canStart,
      fields
    }
  },
  data () {
    return {
      desktopStates,
      status
    }
  },
  computed: {
    ...mapGetters(['getDeployment', 'getDeploymentLoaded', 'getViewers']),
    sortedDesktops () {
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase()) ? -1 : 1
      })
    }
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
  },
  destroyed () {
    this.$store.dispatch('resetDeploymentsState')
  },
  methods: {
    ...mapActions([
      'deleteDesktop',
      'openDesktop',
      'changeDesktopStatus',
      'createDesktop'
    ]),
    imageId (desktop, template) {
      return desktop.id && DesktopUtils.hash(desktop.id)
    },
    hideViewers (desktop) {
      return desktop.state && desktop.type === 'nonpersistent' && this.getItemState(desktop) === desktopStates.stopped
    },
    showDropDown (desktop) {
      return [desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(this.getItemState(desktop))
    },
    getItemState (desktop) {
      return desktop.state ? desktop.state.toLowerCase() : desktopStates.stopped
    },
    buttCssColor (state) {
      const stateColors = {
        stopped: 'btn-green',
        'shutting-down': 'btn-red',
        started: 'btn-red',
        waitingip: 'btn-red',
        error: 'btn-red',
        failed: 'btn-orange'
      }
      return stateColors[state]
    },
    stateCssClass (state) {
      const stateColors = {
        stopped: 'state-off',
        started: 'state-on',
        waitingip: 'state-loading',
        failed: 'state-error',
        working: 'state-loading',
        'shutting-down': 'state-loading'
      }
      return stateColors[state]
    },
    getViewerText (desktop) {
      return this.getDefaultViewer(desktop) !== '' ? i18n.t(`views.select-template.viewer-name.${this.getDefaultViewer(desktop)}`) : i18n.t('views.select-template.viewers')
    },
    getDefaultViewer (desktop) {
      if (desktop.viewers !== undefined) {
        if (this.getViewers[desktop.id] !== undefined && desktop.viewers.includes(this.getViewers[desktop.id])) {
          return this.getViewers[desktop.id]
        } else if (desktop.viewers.length > 0) {
          return desktop.viewers.includes('browser-vnc') ? 'browser-vnc' : desktop.viewers[0]
        }
      }
      return ''
    },
    onClickDesktopVisible (desktop) {
      this.$store.dispatch('toggleDesktopVisible', { id: desktop.id, visible: desktop.visible })
    },
    onClickDeleteDesktop (desktop) {
      if ([desktopStates.failed, desktopStates.stopped].includes(this.getItemState(desktop))) {
        this.$snotify.clear()

        const yesAction = () => {
          this.$snotify.remove()
          this.deleteDesktop({ id: desktop.id })
        }

        const noAction = () => {
          this.$snotify.remove() // default
        }

        this.$snotify.prompt(`${i18n.t('messages.confirmation.delete-deployment-desktop', { name: desktop.userName })}`, {
          position: 'centerTop',
          buttons: [
            { text: 'Yes', action: yesAction, bold: true },
            { text: 'No', action: noAction }
          ],
          placeholder: ''
        })
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.delete-desktop-stop'), '', true, 2000)
      }
    }
  }
}
</script>
