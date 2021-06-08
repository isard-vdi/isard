<template>
  <div class='table-list px-5'>
    <b-container fluid class='px-0'>
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
                :id="'card-info-icon-'"
              ></b-icon>

              <b-tooltip
              :target="'card-info-icon-'"
              :title='data.item.description'
              triggers='hover'
              placement='top'
              custom-class='isard-tooltip-class'></b-tooltip>

              <!-- IMAGE -->
              <div
                class='rounded-circle bg-red'
                :style="{'background-image': 'url(' + require('../assets/img/cards/' + imageId(data.item, data.item.desktop)+ '.jpg') + ')'}"
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
                  <div v-if="data.item.state !== 'Cargando'" :class="'state-dot mr-2 ' + data.item.state"></div>
                  <!-- SPINNER -->
                  <b-spinner
                        v-if="getItemState(data.item) === desktopStates.waitingip"
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
                    cla
                    cssClass='viewers-dropdown flex-grow-1'
                    variant='light'
                    :viewers="data.item.viewers && data.item.viewers.filter(item => item !== viewers[data.item.id])"
                    :desktop="data.item"
                    :viewerText="viewers[data.item.id] !== undefined ? getViewerText(data.item).substring(0, 13) : $t('views.select-template.viewers')"
                    :fullViewerText="viewers[data.item.id] !== undefined ? getViewerText(data.item) : $t('views.select-template.viewers')"
                    :defaultViewer="viewers[data.item.id]"
                    :waitingIp="data.item.state && data.item.state.toLowerCase() === desktopStates.waitingip"
                    @dropdownClicked="openDesktop">
                  </isard-dropdown>
              </div>
            </template>
            <template #cell(action)='data'>
              <DesktopButton v-if="!data.item.state || (data.item.type === 'nonpersistent' && ![desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(getItemState(data.item)))"
                    class="dropdown-text"
                    :active="true"
                    @buttonClicked="chooseDesktop(data.item.id)"
                    :buttColor = "buttCssColor(getItemState(data.item))"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.status.notCreated.action')">
                </DesktopButton>
                <DesktopButton v-if="data.item.type === 'persistent' || (data.item.type === 'nonpersistent' && data.item.state && getItemState(data.item) ===  desktopStates.stopped )"
                    class="dropdown-text"
                    :active="true"
                    @buttonClicked="changeDesktopStatus({ action: status[getItemState(data.item) || 'stopped'].action, desktopId: data.item.id })"
                    :buttColor = "buttCssColor(getItemState(data.item))"
                    :spinnerActive ="false"
                    :buttText = "$t(`views.select-template.status.${getItemState(data.item)}.action`)">
                </DesktopButton>
                <DesktopButton v-if="(data.item.state && data.item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip, desktopStates.stopped].includes(getItemState(data.item)))"
                    class="dropdown-text"
                    :active="true"
                    @buttonClicked="deleteDesktop(data.item.id)"
                    buttColor = "btn-red"
                    :spinnerActive ="false"
                    :buttText = "$t('views.select-template.remove')">
                </DesktopButton>
            </template>
          </b-table>
        </b-col>
      </b-row>
    </b-container>
  </div>
</template>

<script>
import i18n from '@/i18n'
import { desktopStates, status } from '@/shared/constants'
import { DesktopUtils } from '@/utils/desktopsUtils'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import DesktopButton from '@/components/desktops/Button.vue'
import { mapActions } from 'vuex'

export default {
  components: { DesktopButton, IsardDropdown },
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
  created () {
    console.log(this.desktops)
  },
  computed: {
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
    viewers () {
      return this.$store.getters.getViewers
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
        error: 'btn-red'
      }
      return stateColors[state]
    },
    getViewerText (desktop) {
      const name = i18n.t(`views.select-template.viewer-name.${this.viewers[desktop.id]}`)
      return i18n.t('views.select-template.viewer', i18n.locale, { name: name })
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
          label: 'Nombre',
          thStyle: { width: '25%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: 'Descripción',
          thStyle: { width: '35%' },
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
          label: 'Estado',
          thStyle: { width: '10%' },
          tdClass: 'state'
        },
        {
          key: 'viewers',
          thStyle: { width: '7%' },
          label: 'Visor',
          tdClass: 'viewers'
        },
        {
          key: 'action',
          label: 'Acción',
          thStyle: { width: '5%' },
          tdClass: 'px-4 action'
        }
      ]
    }
  }
}
</script>

<style>
/* TYPOGRAPHY */
.table-list .description p {
  font-size: 0.9rem;
}
.table-list .ip p {
  font-size: 0.9rem;
}
.table-list .state p {
  font-size: 0.9rem;
}
.table-list .viewers button {
  font-size: 0.9rem;
}
.table-list .action button p {
  font-size: 0.9rem;
}

/* TABLE */
.table-list table {
  border-collapse: separate;
  border-spacing: 0 1em;
}

.table-list thead tr {
  box-shadow: none !important;
}

.table-list thead th {
  border-top: 0 !important;
  border-bottom: 0 !important;
  border-right: 1px solid #dfe6e9;
}

.table-list thead th:last-child {
  border-right: 0;
}

.table-list tr {
  box-shadow: 0 2px 4px 0 #b2bec3;
  margin-bottom: 20px;
  border-radius: 11px;
}

.table-list tr td {
  border: 0;
  border-right: 1px solid #e6edf0;
  vertical-align: middle;
}

.table-list tr td.image > div{
  width: 60px;
  height: 60px;
  left: 0;
  top: 16px;
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center;
  background-color: white;
  border-radius: 50%;
}

.table-list .ip,
.table-list .viewers {
  text-align: center;
}

/* VIEWERS */
.table-list .viewers-dropdown>button {
  display: flex;
  justify-content: space-between;
  border-radius: 7px;
  border: 1px solid #b2bec3;
  padding-left: 10px;
}

.table-list .viewers-dropdown>button::after {
  margin-top: 0.7em;
}

.table-list .viewers-dropdown ul.dropdown-menu {
  padding: 0;
}

.table-list .viewers-dropdown ul.dropdown-menu a {
  padding: 3px 10px;
}

.table-list .viewers-dropdown ul.dropdown-menu li:not(:first-child) {
  border-top: 1px solid lightgray;
}

/* STATE */
.table-list .state-on {
  background-color: #97c277;
}

.table-list .state-off {
  background-color: #dde4e4;
}

.table-list .state-error {
  background-color: #e7898e;
}

.table-list .state-loading {
  background-color: #eead47;
}

.table-list .state-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
}

.table-list .state-dot.state-on {
  background-color: #97c277;
}

.table-list .state-dot.state-off {
  background-color: #dde4e4;
}

.table-list .state-dot.state-error {
  background-color: #e7898e;
}

.table-list .state-dot.state-loading {
  background-color: #eead47;
}

/* INFO ICON */
.table-list .info-icon {
  top: 5px;
  left: 5px;
  fill: #b2bec3;
}

/* SPINNER */
.spinner-loading {
  color: #eead47;
}

/* BUTTONS */
.table-list .action button svg {
  height: 20px;
}

.table-list .action button p {
  margin-top: -3px !important;
}
</style>
