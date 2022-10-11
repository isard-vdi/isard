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
        <b-row>
          <b-col
            cols="12"
            class="py-3 p-5 pt-4 d-flex flex-row flex-wrap justify-content-start"
          >
            <b-table
              :items="desktops"
              :fields="fields"
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
                <div class="d-flex justify-content-center align-items-center">
                  <!-- STATE DOT -->
                  <div
                    v-if="![desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(getItemState(data.item))"
                    :class="'state-dot mr-2 ' + stateCssClass(getItemState(data.item))"
                  />
                  <!-- SPINNER -->
                  <b-spinner
                    v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(getItemState(data.item))"
                    small
                    class="align-self-center mr-2 spinner-loading"
                  />
                  <!-- TITLE -->
                  <p class="mb-0 text-medium-gray flex-grow">
                    {{ data.item.type === 'nonpersistent' && getItemState(data.item) === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${getItemState(data.item)}.text`) }}
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
                <!-- Main action button persistent-->
                <DesktopButton
                  v-if="(data.item.type === 'persistent' || (data.item.type === 'nonpersistent' && data.item.state && getItemState(data.item) === desktopStates.stopped )) && ![desktopStates.working].includes(getItemState(data.item))"
                  class="table-action-button"
                  :active="true"
                  :button-class="buttCssColor(getItemState(data.item))"
                  :spinner-active="false"
                  :butt-text="$t(`views.select-template.status.${getItemState(data.item)}.action`)"
                  :icon-name="data.item.buttonIconName"
                  @buttonClicked="changeDesktopStatus({ action: status[getItemState(data.item) || 'stopped'].action, desktopId: data.item.id })"
                />
                <!-- Delete action button-->
                <DesktopButton
                  v-if="(data.item.state && data.item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(getItemState(data.item)))"
                  class="table-action-button"
                  :active="true"
                  button-class="btn-red"
                  :spinner-active="false"
                  :butt-text="$t('views.select-template.remove')"
                  icon-name="trash"
                  @buttonClicked="deleteNonpersistentDesktop(data.item.id)"
                />
              </template>
              <template #cell(options)="data">
                <div class="d-flex align-items-center">
                  <b-button
                    :title="$t('components.desktop-cards.actions.edit')"
                    class="rounded-circle btn-blue px-2 mr-2"
                    @click="onClickGoToEditDesktop({itemId: data.item.id, returnPage: currentRouteName})"
                  >
                    <b-icon
                      icon="pencil-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.type === 'persistent'"
                    :title="$t('components.desktop-cards.actions.delete')"
                    class="rounded-circle btn-red px-2 mr-2"
                    @click="onClickDeleteDesktop(data.item)"
                  >
                    <b-icon
                      icon="trash-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="getUser.role_id != 'user' && data.item.type === 'persistent'"
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
                    v-if="getUser.role_id != 'user'"
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
                    v-if="data.item.needsBooking"
                    :title="$t('components.desktop-cards.actions.booking')"
                    class="rounded-circle btn-orange px-2 mr-2"
                    @click="onClickBookingDesktop(data.item)"
                  >
                    <b-icon
                      icon="calendar"
                      scale="0.75"
                    />
                  </b-button>
                </div>
              </template>
            </b-table>
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
  data () {
    return {
      desktopStates,
      status,
      fields: [
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
          thStyle: { width: '30%' },
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
          thStyle: { width: '15%' },
          label: `${i18n.t('components.desktop-cards.table-header.viewers')}`,
          tdClass: 'viewers'
        },
        {
          key: 'action',
          label: `${i18n.t('components.desktop-cards.table-header.action')}`,
          thStyle: { width: '10%' },
          tdClass: 'px-4 action'
        },
        {
          key: 'options',
          label: '',
          thStyle: { width: '5%' },
          thClass: `${this.desktops[0].type === 'persistent' ? '' : 'd-none'}`,
          tdClass: `${this.desktops[0].type === 'persistent' ? '' : 'd-none'}`
        }
      ]
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
      'changeDesktopStatus',
      'createDesktop',
      'navigate',
      'goToItemBooking',
      'goToEditDomain',
      'fetchDirectLink',
      'checkCreateTemplateQuota'
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
      return [desktopStates.started, desktopStates.waitingip].includes(this.getItemState(desktop))
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
        failed: 'btn-red'
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
      const name = this.getDefaultViewer(desktop) !== '' ? i18n.t(`views.select-template.viewer-name.${this.getDefaultViewer(desktop)}`) : i18n.t('views.select-template.viewers')
      return this.getDefaultViewer(desktop) !== '' ? i18n.t('views.select-template.viewer', i18n.locale, { name: name }) : name
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
        this.checkCreateTemplateQuota(desktop.id)
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
      this.$snotify.clear()

      const yesAction = () => {
        this.$snotify.remove()
        this.deleteDesktop(desktop.id)
      }

      const noAction = () => {
        this.$snotify.remove() // default
      }

      this.$snotify.prompt(`${i18n.t('messages.confirmation.delete-desktop', { name: desktop.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    },
    onClickBookingDesktop (desktop) {
      const data = { id: desktop.id, type: 'desktop', name: desktop.name }
      this.goToItemBooking(data)
    },
    onClickOpenDirectViewerModal (desktopId) {
      this.fetchDirectLink(desktopId)
    }
  }
}
</script>
