<template>
  <div class="table-list px-5">
    <b-container
      fluid
      class="px-0 pt-2"
    >
      <b-skeleton-wrapper
        :loading="loading"
        class="pb-1 pt-4 justify-content-start"
      >
        <template #loading>
          <b-col>
            <list-item-skeleton class="mb-2" />
            <list-item-skeleton class="mb-2" />
            <list-item-skeleton class="mb-2" />
          </b-col>
        </template>
        <b-row class="mt-4">
          <b-row
            class="ml-auto mr-2"
          >
            <b-col>
              <b-form-group
                :label="$t('forms.show-pages')"
                label-for="per-page-select"
                label-cols-md="5"
                label-align-sm="right"
                class="text-medium-gray mr-2 mr-lg-0"
              >
                <b-form-select
                  id="per-page-select"
                  v-model="perPage"
                  :label="$t('forms.show-pages')"
                  :options="pageOptions"
                  size="sm"
                />
              </b-form-group>
            </b-col>
            <b-col>
              <b-pagination
                v-model="currentPage"
                :total-rows="totalRows"
                :per-page="perPage"
                aria-controls="desktops-table"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>
        <b-row>
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-end"
          >
            <b-table
              id="desktops-table"
              :items="desktops"
              :fields="fields"
              :responsive="true"
              :per-page="perPage"
              :current-page="currentPage"
              :tbody-tr-class="rowClass"
            >
              <template #cell(image)="data">
                <!-- INFO -->
                <b-icon
                  v-b-tooltip="{ title: `${data.item.description ? data.item.description : $t(`components.desktop-cards.no-info-default`)}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
                  icon="info-circle-fill"
                  class="info-icon position-absolute cursor-pointer"
                />
                <!-- IMAGE -->
                <div
                  class="rounded-circle bg-red"
                  :style="{'background-image': `url('..${data.item.image.url}')`}"
                />
              </template>
              <template #cell(name)="data">
                <p class="m-0 font-weight-bold">
                  {{ data.item.name }}
                </p>
              </template>
              <template #cell(description)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.description }}
                </p>
              </template>
              <template #cell(ip)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.ip }}
                </p>
              </template>
              <template #cell(state)="data">
                <span class="d-flex flex-column justify-content-center">
                  <div
                    v-b-tooltip="{title: `${data.item.currentAction && getItemState(data.item)==desktopStates.maintenance ? $t('components.desktop-cards.storage-operation.'+data.item.currentAction, { action: data.item.currentAction} ) : ''}`}"
                    class="d-flex justify-content-center align-items-center"
                  >
                    <!-- STATE DOT -->
                    <div
                      v-if="![desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down'], desktopStates.downloading, desktopStates.maintenance].includes(getItemState(data.item))"
                      :class="'state-dot mr-2 ' + stateCssClass(getItemState(data.item))"
                    />
                    <!-- SPINNER -->
                    <b-spinner
                      v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down'], desktopStates.downloading, desktopStates.maintenance].includes(getItemState(data.item))"
                      small
                      class="align-self-center mr-2 spinner-loading"
                    />
                    <!-- TITLE -->
                    <p class="mb-0 text-medium-gray flex-grow">
                      {{ data.item.type === 'nonpersistent' && getItemState(data.item) === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${getItemState(data.item)}.text`) }}
                    </p>
                  </div>
                  <p
                    v-if="
                      [desktopStates.downloading, desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down'], desktopStates.maintenance].includes(getItemState(data.item))
                        && data.item.queue && ![0].includes(data.item.queue || 0)
                    "
                    class="mb-0 text-state-small font-weight-bold"
                    :class="statusTextCssColor"
                  >
                    {{ $t('components.desktop-cards.queue', { position: data.item.queue || 0 }) }}
                  </p>
                </span>
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
                    @notifyWaitingIp="notifyWaitingIp"
                  />
                </div>
              </template>
              <template #cell(action)="data">
                <!-- Main action button nonpersistent -->
                <DesktopButton
                  v-if="!data.item.state"
                  class="table-action-button"
                  :active="true"
                  :button-class="buttCssColor(getItemState(data.item))"
                  :spinner-active="false"
                  :butt-text="$t('views.select-template.status.notCreated.action')"
                  :icon-name="data.item.buttonIconName"
                  @buttonClicked="chooseDesktop(data.item.id)"
                />

                <div
                  v-if="data.item.progress"
                >
                  <small>{{ data.item.progress.size }} - {{ data.item.progress.throughput_average }}/s - {{ data.item.progress.time_left }} </small>
                  <b-progress
                    :max="100"
                    animated
                    height="2rem"
                  >
                    <b-progress-bar
                      variant="secondary"
                      :value="data.item.progress.percentage"
                      show-progress
                      animated
                    >
                      <strong>{{ data.item.progress.percentage }}%</strong>
                    </b-progress-bar>
                  </b-progress>
                </div>

                <!-- Main action button persistent-->
                <span
                  v-b-tooltip.hover="data.item.needsBooking ? { title: `${getTooltipTitle(data.item.nextBookingStart, data.item.nextBookingEnd)}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' } : ''"
                >
                  <DesktopButton
                    v-if="(data.item.type === 'persistent' || (data.item.type === 'nonpersistent' && data.item.state && getItemState(data.item) === desktopStates.stopped )) && ![desktopStates.working, desktopStates.downloading].includes(getItemState(data.item))"
                    class="table-action-button"
                    :active="true"
                    :button-class="buttCssColor(getItemState(data.item))"
                    :spinner-active="false"
                    :butt-text="$t(`views.select-template.status.${getItemState(data.item)}.action`)"
                    :icon-name="data.item.buttonIconName"
                    @buttonClicked="changeDesktopStatus(data.item, { action: status[getItemState(data.item) || 'stopped'].action, desktopId: data.item.id, storage: data.item.storage })"
                  />
                  <!-- Delete action button-->
                  <DesktopButton
                    v-if="(data.item.state && data.item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(getItemState(data.item)))"
                    class="table-action-button"
                    :active="true"
                    button-class="btn-red"
                    :spinner-active="false"
                    :butt-text="$t('views.select-template.remove')"
                    icon-name="x"
                    @buttonClicked="deleteNonpersistentDesktop(data.item.id)"
                  />
                </span>
              </template>
              <template #cell(options)="data">
                <div
                  v-if="data.item.type === 'persistent'"
                  class="d-flex align-items-center"
                >
                  <b-button
                    v-if="data.item.editable"
                    :title="$t('components.desktop-cards.actions.edit')"
                    class="rounded-circle btn-blue px-2 mr-2"
                    @click="onClickGoToEditDesktop({itemId: data.item.id, returnPage: currentRouteName, server: data.item.server, state: data.item.state})"
                  >
                    <b-icon
                      icon="pencil-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.editable"
                    :title="$t('components.desktop-cards.actions.delete')"
                    class="rounded-circle btn-red px-2 mr-2"
                    @click="onClickDeleteDesktop(data.item)"
                  >
                    <b-icon
                      icon="x"
                      scale="1"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.editable && getUser.role_id != 'user' && data.item.type === 'persistent'"
                    :title="$t('components.desktop-cards.actions.template')"
                    class="rounded-circle btn-green px-2 mr-2"
                    style="width: 36px; height: 36px"
                    @click="onClickGoToNewTemplate(data.item)"
                  >
                    <font-awesome-icon
                      :icon="['fas', 'cubes']"
                      class="text-white"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.editable && getUser.role_id != 'user'"
                    :title="$t('components.desktop-cards.actions.direct-link')"
                    class="rounded-circle btn-purple px-2 mr-2"
                    @click="onClickOpenDirectViewerModal(data.item.id)"
                  >
                    <b-icon
                      icon="link45deg"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.editable && data.item.needsBooking"
                    :title="$t('components.desktop-cards.actions.booking')"
                    class="rounded-circle btn-orange px-2 mr-2"
                    @click="onClickBookingDesktop(data.item)"
                  >
                    <b-icon
                      icon="calendar"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="!data.item.editable && data.item.permissions.includes('recreate')"
                    :title="$t('components.desktop-cards.actions.recreate')"
                    class="rounded-circle btn-orange px-2 mr-2"
                    @click="onClickRecreateDesktop(desktop = data.item)"
                  >
                    <b-icon
                      icon="arrow-counterclockwise"
                      scale="0.75"
                    />
                  </b-button>
                </div>
              </template>
            </b-table>
            <b-row class="mt-4">
              <b-row
                class="ml-auto mr-2"
              >
                <b-col>
                  <b-form-group
                    :label="$t('forms.show-pages')"
                    label-for="per-page-select"
                    label-cols-md="5"
                    label-align-sm="right"
                    class="text-medium-gray mr-2 mr-lg-0"
                  >
                    <b-form-select
                      id="per-page-select"
                      v-model="perPage"
                      :label="$t('forms.show-pages')"
                      :options="pageOptions"
                      size="sm"
                    />
                  </b-form-group>
                </b-col>
                <b-col>
                  <b-pagination
                    v-model="currentPage"
                    :total-rows="totalRows"
                    :per-page="perPage"
                    aria-controls="desktops-table"
                    size="sm"
                  />
                </b-col>
              </b-row>
            </b-row>
          </b-col>
        </b-row>
      </b-skeleton-wrapper>
    </b-container>
  </div>
</template>

<script>
import i18n from '@/i18n'
import { desktopStates, status } from '@/shared/constants'
import { DesktopUtils } from '@/utils/desktopsUtils'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { mapActions, mapGetters } from 'vuex'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import { ErrorUtils } from '@/utils/errorUtils'
import { ref, watch } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'

export default {
  components: { DesktopButton, IsardDropdown, ListItemSkeleton },
  props: {
    listTitle: String,
    templates: {
      required: true,
      type: Array
    },
    desktops: {
      required: true,
      type: Array
    },
    persistent: {
      required: true,
      type: Boolean
    },
    loading: {
      required: true,
      type: Boolean
    }
  },
  setup (props, context) {
    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const currentPage = ref(1)
    const totalRows = ref(props.desktops.length)

    watch(() => props.desktops, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })

    const desktopFields = [
      {
        key: 'image',
        sortable: false,
        label: '',
        thStyle: { width: '5%' },
        tdClass: 'image position-relative'
      },
      {
        key: 'name',
        sortable: true,
        label: `${i18n.t('components.desktop-cards.table-header.name')}`,
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'description',
        sortable: true,
        label: `${i18n.t('components.desktop-cards.table-header.description')}`,
        thStyle: { width: '25%' },
        tdClass: 'description'
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
        label: `${i18n.t('components.desktop-cards.table-header.state')}`,
        thStyle: { width: '10%' },
        tdClass: 'state'
      },
      {
        key: 'viewers',
        thStyle: { width: '10%' },
        label: `${i18n.t('components.desktop-cards.table-header.viewers')}`,
        tdClass: 'viewers'
      },
      {
        key: 'action',
        label: `${i18n.t('components.desktop-cards.table-header.action')}`,
        thStyle: { width: '15%' },
        tdClass: 'px-4 action'
      },
      {
        key: 'options',
        label: '',
        thStyle: { width: '5%' },
        thClass: `${props.desktops[0].type === 'persistent' ? '' : 'd-none'}`,
        tdClass: `${props.desktops[0].type === 'persistent' ? '' : 'd-none'}`
      }
    ]

    const $store = context.root.$store

    const changeDesktopStatus = (desktop, data) => {
      if (data.action === 'cancel') {
        $store.dispatch('cancelOperation', data)
      } else if (canStart(desktop) || data.action !== 'start') {
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

    const rowClass = (item, type) => {
      if (!item || type !== 'row') return
      if (item.needsBooking) return 'list-orange-bar'
    }

    const notifyWaitingIp = () => {
      $store.dispatch('showNotification', { message: i18n.t('messages.info.warning-desktop-waiting-ip') })
    }

    return {
      perPage,
      pageOptions,
      currentPage,
      totalRows,
      fields: desktopFields,
      canStart,
      changeDesktopStatus,
      rowClass,
      notifyWaitingIp
    }
  },
  data () {
    return {
      desktopStates,
      status
    }
  },
  computed: {
    ...mapGetters(['getViewers', 'getUser']),
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
      'goToItemBooking',
      'goToEditDomain',
      'fetchDirectLink',
      'goToNewTemplate',
      'updateDesktopModal',
      'recreateDesktop'
    ]),
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
    imageId (desktop, template) {
      return desktop.state && desktop.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(this.getItemState(desktop)) ? DesktopUtils.hash(this.getemplate.id) : desktop.id && DesktopUtils.hash(desktop.id)
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
    getemplate (desktop) {
      return (desktop.template && this.templates.filter(template => template.id === this.desktop.template)[0]) || {}
    },
    buttCssColor (state) {
      const stateColors = {
        stopped: 'btn-green',
        'shutting-down': 'btn-red',
        started: 'btn-red',
        waitingip: 'btn-red',
        error: 'btn-red',
        failed: 'btn-orange',
        maintenance: 'btn-red'
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
        'shutting-down': 'state-loading',
        maintenance: 'state-loading'
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
    onClickGoToNewTemplate (desktop) {
      if (desktop.server) {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.new-template-server'), '', true, 2000)
      } else if (this.getItemState(desktop) === desktopStates.stopped) {
        this.goToNewTemplate(desktop.id)
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.new-template-stop'), '', true, 2000)
      }
    },
    onClickGoToEditDesktop (desktop) {
      if (desktop.server && this.getItemState(desktop) !== desktopStates.failed) {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.edit-desktop-server'), '', true, 2000)
      } else if ([desktopStates.failed, desktopStates.stopped].includes(this.getItemState(desktop))) {
        this.goToEditDomain(desktop.itemId)
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.edit-desktop-stop'), '', true, 2000)
      }
    },
    onClickDeleteDesktop (desktop) {
      if ([desktopStates.failed, desktopStates.stopped].includes(this.getItemState(desktop))) {
        this.updateDesktopModal({
          show: true,
          type: 'delete',
          item: {
            id: desktop.id
          },
          tag: desktop.tag
        })
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.delete-desktop-stop'), '', true, 2000)
      }
    },
    onClickBookingDesktop (desktop) {
      const data = { id: desktop.id, type: 'desktop', name: desktop.name }
      this.goToItemBooking(data)
    },
    onClickOpenDirectViewerModal (desktopId) {
      this.fetchDirectLink(desktopId)
    },
    getTooltipTitle (dateStart, dateEnd) {
      if (DateUtils.dateIsAfter(dateEnd, new Date()) && DateUtils.dateIsBefore(dateStart, new Date())) {
        return i18n.t('components.desktop-cards.notification-bar.booking-ends') + DateUtils.formatAsTime(dateEnd) + ' ' + DateUtils.formatAsDayMonth(dateEnd)
      } else if (dateStart) {
        return i18n.t('components.desktop-cards.notification-bar.next-booking') + ': ' + DateUtils.formatAsTime(dateStart) + ' ' + DateUtils.formatAsDayMonth(dateStart)
      } else {
        return i18n.t('components.desktop-cards.notification-bar.no-next-booking')
      }
    },
    onClickRecreateDesktop (payload) {
      if (this.getItemState(payload) === desktopStates.stopped) {
        // return
        this.$snotify.clear()

        const yesAction = () => {
          this.$snotify.clear()
          this.recreateDesktop({ id: payload.id })
        }

        const noAction = (toast) => {
          this.$snotify.clear()
        }

        this.$snotify.prompt(`${i18n.t('messages.confirmation.recreate-desktop', { name: payload.name })}`, {
          position: 'centerTop',
          buttons: [
            { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
            { text: `${i18n.t('messages.no')}`, action: noAction }
          ],
          placeholder: ''
        })
      } else {
        ErrorUtils.showInfoMessage(this.$snotify, i18n.t('messages.info.recreate-desktop-stop'), '', true, 2000)
      }
    }
  }
}
</script>
