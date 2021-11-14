<template>
  <div class='table-list px-5'>
    <b-container fluid class='px-0 pt-2'>
      <b-skeleton-wrapper :loading="loading" class='pb-1 pt-4 justify-content-start'>
              <template #loading>
                <b-col>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                </b-col>
              </template>
      <b-row>
        <b-col
          cols='12'
          class='py-3 p-5 pt-4 d-flex flex-row flex-wrap justify-content-start'
        >
          <b-table :items='desktops' :fields='fields'>
            <template #cell(image)='data'>
              <!-- INFO -->
              <b-icon
                icon='info-circle-fill'
                class='info-icon position-absolute cursor-pointer'
                v-b-tooltip="{ title: `${data.item.description ? data.item.description : $t(`components.desktop-cards.no-info-default`)}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
              ></b-icon>
              <!-- IMAGE -->
              <div
                class='rounded-circle bg-red'
                :style="{'background-image': `url('..${data.item.image.url}')`}"
              ></div>
            </template>
            <template #cell(name)='data'>
              <p class='m-0 font-weight-bold'>
                {{ data.item.name }}
              </p>
            </template>
            <template #cell(description)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.description }}
              </p>
            </template>
            <template #cell(ip)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.ip }}
              </p>
            </template>
            <template #cell(state)='data'>
              <div class='d-flex justify-content-center align-items-center'>
                <!-- STATE DOT -->
                  <div v-if="![desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(getItemState(data.item))" :class="'state-dot mr-2 ' + stateCssClass(getItemState(data.item))"></div>
                  <!-- SPINNER -->
                  <b-spinner
                        v-if="[desktopStates.waitingip, desktopStates.working, desktopStates['shutting-down']].includes(getItemState(data.item))"
                        small
                        class='align-self-center mr-2 spinner-loading'
                      ></b-spinner>
                      <!-- TITLE -->
                  <p class='mb-0 text-medium-gray flex-grow'>
                    {{ data.item.type === 'nonpersistent' && getItemState(data.item) === desktopStates.stopped ? $t(`views.select-template.status.readyCreation.text`) : $t(`views.select-template.status.${getItemState(data.item)}.text`)}}
                  </p>
              </div>
            </template>
            <template #cell(viewers)="data">
              <div class=''>
                <DesktopButton
                    v-if="!hideViewers && data.item.viewers !== undefined && data.item.viewers.length === 1"
                    :active="getItemState(data.item) === desktopStates.started"
                    :buttColor = "buttViewerCssColor"
                    :buttText="data.item.viewers[0]"
                    variant="primary"
                    :spinnerActive="waitingIp"
                    @buttonClicked="openDesktop({desktopId: data.item.id, viewer: data.item.viewers && data.item.viewers[0]})">
                  </DesktopButton>
                  <isard-dropdown
                    v-else
                    :ddDisabled="!showDropDown(data.item)"
                    :class="{ 'dropdown-inactive': !showDropDown(data.item) }"
                    cssClass='viewers-dropdown flex-grow-1'
                    variant='light'
                    :viewers="data.item.viewers && data.item.viewers.filter(item => item !== getDefaultViewer(data.item))"
                    :desktop="data.item"
                    :viewerText="getViewerText(data.item).substring(0, 40)"
                    fullViewerText=''
                    :defaultViewer="getDefaultViewer(data.item)"
                    :waitingIp="data.item.state && data.item.state.toLowerCase() === desktopStates.waitingip"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>
              </div>
            </template>
            <template #cell(action)='data'>
               <!-- Main action button nonpersistent -->
              <DesktopButton v-if="!data.item.state"
                    class="table-action-button"
                    :active="true"
                    @buttonClicked="chooseDesktop(data.item.id)"
                    :buttColor = "buttCssColor(getItemState(data.item))"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.status.notCreated.action')"
                    :iconName = "data.item.buttonIconName">
                </DesktopButton>
                <!-- Main action button persistent-->
                <DesktopButton v-if="(data.item.type === 'persistent' || (data.item.type === 'nonpersistent' && data.item.state && getItemState(data.item) ===  desktopStates.stopped )) && ![desktopStates.working, desktopStates['shutting-down']].includes(getItemState(data.item))"
                    class="table-action-button"
                    :active="true"
                    @buttonClicked="changeDesktopStatus({ action: status[getItemState(data.item) || 'stopped'].action, desktopId: data.item.id })"
                    :buttColor = "buttCssColor(getItemState(data.item))"
                    :spinnerActive ="false"
                    :buttText = "$t(`views.select-template.status.${getItemState(data.item)}.action`)"
                    :iconName = "data.item.buttonIconName">
                </DesktopButton>
                <!-- Delete action button-->
                <DesktopButton v-if="(data.item.state && data.item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(getItemState(data.item)))"
                    class="table-action-button"
                    :active="true"
                    @buttonClicked="deleteDesktop(data.item.id)"
                    buttColor = "btn-red"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.remove')"
                    iconName = "trash">
                </DesktopButton>
            </template>
            <template #cell(delete)='data'>
              <div class='d-flex justify-content-center align-items-center'>
                <a class='cursor-pointer' @click="onClickDeleteDesktop(data.item)"><b-icon icon="trash" variant="danger"></b-icon></a>
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

export default {
  components: { DesktopButton, IsardDropdown, ListItemSkeleton },
  setup () {},
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
  computed: {
    ...mapGetters(['getViewers']),
    stateBarCssClass () {
      const states = {
        stopped: 'state-off',
        started: 'state-on',
        waitingip: 'state-loading',
        error: 'state-error',
        failed: 'state-failed'
      }
      return states[this.desktopState]
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
          { text: 'Yes', action: yesAction, bold: true },
          { text: 'No', action: noAction }
        ],
        placeholder: ''
      })
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
          key: 'delete',
          label: '',
          thStyle: { width: '5%' },
          thClass: `${this.desktops[0].type === 'persistent' ? '' : 'd-none'}`,
          tdClass: `${this.desktops[0].type === 'persistent' ? '' : 'd-none'}`
        }
      ]
    }
  },
  destroyed () {
    this.$snotify.clear()
  }
}
</script>
