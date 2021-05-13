<template>
    <b-container fluid>
      <!-- Button view -->
      <transition-group v-if="gridView" appear name="bounce">
        <!-- Persistent desktops -->
        <b-row v-if="persistent" key="persistent" align-h="center">
          <b-card
            v-for="desktop in desktops"
            :key="desktop.id" class="shadow persistent_desktop m-3 border-secondary" no-body>
              <b-card-body :class="desktop.template && templates.filter(template => template.id ===  desktop.template).length > 0 ? '' : 'mt-4'">
                <font-awesome-icon size="4x" :icon="ICONS[desktop.icon]" class="mb-2"/>
                <b-card-title class="card-title">
                    <b-icon v-if="desktop.description" v-b-tooltip.hover :title="desktop.description" icon="info-circle" class="mr-1"></b-icon>
                    {{ desktop.name }}
                </b-card-title>
                <b-card-sub-title class="mb-2 card-sub-title">
                    {{$t(`views.select-template.status.${desktop.state.toLowerCase()}.text`)}}
                    <p v-if="desktop.ip">IP: {{ desktop.ip }}</p>
                </b-card-sub-title>
                <!-- Viewers button/dropdown -->
                <span v-if="desktop.state.toLowerCase() == 'started'">
                  <isard-button
                    v-if="desktop.viewers.length === 1"
                    :viewerName="desktop.viewers[0]"
                    variant="primary" cssClass="m-1"
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
        </b-row>
        <!-- Non persistent desktops -->
        <b-row v-else key="nonpersistent" align-h="center">
          <b-card v-for="desktop in desktops" :key="desktop.id" class="shadow temporal_desktop m-3" no-body>
            <b-card-body>
              <b-row no-gutters>
                <b-col cols="4">
                  <font-awesome-icon class="mt-2" size="4x" :icon="ICONS[desktop.icon]" />
                </b-col>
                <b-col cols="8">
                  <b-card-title class="card-title">
                      <b-icon v-if="desktop.description" v-b-tooltip.hover :title="desktop.description" icon="info-circle" class="mr-1"></b-icon>
                      {{desktop.state ? templates.filter(template => template.id ===  desktop.template)[0].name : desktop.name}}
                  </b-card-title>
                  <b-card-sub-title class="card-sub-title" v-if="desktop.state">
                      {{$t(`views.select-template.status.${desktop.state.toLowerCase()}.text`)}}
                      <p v-if="desktop.ip">IP: {{ desktop.ip }}</p>
                  </b-card-sub-title>
                  <!-- If the desktop doesn't exist we can create it using its template id -->
                  <b-button
                    v-if="!desktop.state" size="sm"
                    :variant="status.notCreated.variant"
                    @click="chooseDesktop(desktop.id)">
                      <font-awesome-icon :icon="status.notCreated.icon" class="mr-2"/>
                      {{$t('views.select-template.status.notCreated.action')}}
                  </b-button>
                  <span v-else>
                    <!-- If it's stopped we can start it -->
                    <b-button v-if="desktop.state.toLowerCase() === 'stopped'" size="sm" :variant="status.stopped.variant"
                      @click="changeDesktopStatus({ action: status.stopped.action, desktopId: desktop.id })">
                        <font-awesome-icon :icon="status.stopped.icon" class="mr-2"/>
                        {{$t('views.select-template.status.stopped.action')}}
                    </b-button>
                    <!-- If it's executing we can use its viewers -->
                    <span v-else-if="desktop.state.toLowerCase() === 'started'">
                      <isard-button
                        v-if="desktop.viewers.length === 1"
                        variant="primary"
                        :viewerName="desktop.viewers[0]"
                        cssClass="m-1"
                        @buttonClicked="openDesktop({desktopId: desktop.id, viewer: desktop.viewers[0], template: desktop.template})">
                      </isard-button>
                      <isard-dropdown
                        v-else
                        variant="primary"
                        cssClass="m-1"
                        :viewers="desktop.viewers.filter(item => item !== viewers[desktop.template])"
                        :desktop="desktop"
                        :viewerText="viewers[desktop.template] !== undefined ? getViewerText(viewers[desktop.template]) : $t('views.select-template.viewers')"
                        :defaultViewer="viewers[desktop.template]"
                        :template="desktop.template"
                        @dropdownClicked="openDesktop">
                      </isard-dropdown>
                    </span>
                    <!-- We can remove it anyways -->
                    <b-button variant="danger" size="sm" @click="deleteDesktop(desktop.id)" class="m-1">
                      <font-awesome-icon :icon="['fas', 'trash']" class="mr-2"/>
                      {{ $t('views.select-template.remove') }}
                    </b-button>
                  </span>
                </b-col>
              </b-row>
            </b-card-body>
          </b-card>
        </b-row>
      </transition-group>
      <!-- Table view -->
      <b-row v-else>
        <b-table v-if="persistent" :items="desktops" :fields="table_fields"
        id="desktops-table" class="text-left" key="desktops_table" responsive>
          <!-- Persistent desktops -->
          <template #cell(action)="data">
              <b-button v-if="['started','stopped','waitingip'].includes(data.item.state.toLowerCase())" :variant="status[data.item.state.toLowerCase()].variant"
              @click="changeDesktopStatus({action: status[data.item.state.toLowerCase()].action, desktopId: data.item.id})">
                <font-awesome-icon :icon="status[data.item.state.toLowerCase()].icon" class="mr-2"/>
                {{$t(`views.select-template.status.${data.item.state.toLowerCase()}.action`)}}
              </b-button>
          </template>
          <template #cell(viewers)="data">
            <div v-if="data.item.state.toLowerCase() == 'started'">
              <isard-button
                v-if="data.item.viewers.length === 1"
                variant="primary"
                :viewerName="data.item.viewers[0]"
                @buttonClicked="openDesktop({desktopId: data.item.id, viewer: data.item.viewers[0]})">
              </isard-button>
              <isard-dropdown
                v-else
                variant="primary"
                cssClass="sm"
                :viewers="data.item.viewers.filter(item => item !== viewers[data.item.id])"
                :desktop="data.item"
                :viewerText="viewers[data.item.id] !== undefined ? getViewerText(viewers[data.item.id]) : $t('views.select-template.viewers')"
                :defaultViewer="viewers[data.item.id]"
                @dropdownClicked="openDesktop">
              </isard-dropdown>
            </div>
          </template>
          <template #cell(name)="data">
            <b-row>
              <font-awesome-icon :icon="ICONS[data.item.icon]" size="2x" class="mr-2"/>
              <b-col class="pt-1">
                <p>{{ data.item.name }}</p>
              </b-col>
            </b-row>
          </template>
        </b-table>
        <!-- Non persistent desktops -->
        <b-table v-else :items="desktops" :fields="table_fields"
        id="desktops-table" class="text-left" key="desktops_table" responsive>
          <template #cell(action)="data">
            <!-- If the desktop doesn't exist we can create it using its template id -->
            <b-button
              v-if="!data.item.state"
              :variant="status.notCreated.variant"
              @click="chooseDesktop(data.item.id)" class="mr-1">
                <font-awesome-icon :icon="status.notCreated.icon" class="mr-2"/>
                {{$t('views.select-template.status.notCreated.action')}}
            </b-button>
            <span v-else>
              <!-- If it's stopped we can start it -->
              <b-button
                v-if="data.item.state.toLowerCase() === 'stopped'"
                :variant="status.stopped.variant" class="mr-1"
                @click="changeDesktopStatus({ action: status.stopped.action, desktopId: data.item.id })">
                  <font-awesome-icon :icon="status.stopped.icon" class="mr-2"/>
                  {{$t('views.select-template.status.stopped.action')}}
              </b-button>
              <!-- We can delete it anyways -->
              <b-button variant="danger" @click="deleteDesktop(data.item.id)">
                <font-awesome-icon :icon="['fas', 'trash']" class="mr-2"/>
                {{ $t('views.select-template.remove') }}
              </b-button>
            </span>
          </template>
          <template #cell(viewers)="data">
            <div v-if="data.item.state && data.item.state.toLowerCase() == 'started'">
                <isard-button
                  v-if="data.item.viewers.length === 1"
                  variant="primary"
                  :viewerName="data.item.viewers[0]"
                  @buttonClicked="openDesktop({desktopId: data.item.id, viewer: data.item.viewers[0], template: data.item.template})">
                </isard-button>
                <isard-dropdown
                  v-else
                  variant="primary"
                  cssClass="sm"
                  :viewers="data.item.viewers.filter(item => item !== viewers[data.item.template])"
                  :desktop="data.item"
                  :viewerText="viewers[data.item.template] !== undefined ? getViewerText(viewers[data.item.template]) : $t('views.select-template.viewers')"
                  :defaultViewer="viewers[data.item.template]"
                  :template="data.item.template"
                  @dropdownClicked="openDesktop">
                </isard-dropdown>
            </div>
          </template>
          <template #cell(name)="data">
            <b-row>
              <font-awesome-icon :icon="ICONS[data.item.icon]" size="2x" class="mr-2"/>
              <b-col class="pt-1">
                <p>{{data.item.state ? templates.filter(template => template.id ===  data.item.template)[0].name : data.item.name}}</p>
              </b-col>
            </b-row>
          </template>
          <template #cell(status)="data">
            <span v-if="data.item.state">{{$t(`views.select-template.status.${data.item.state.toLowerCase()}.text`)}}</span>
          </template>
        </b-table>
      </b-row>
    </b-container>
</template>

<script>
// @ is an alias to /src
import i18n from '@/i18n'
import { mapActions } from 'vuex'
import { cardIcons } from '../shared/constants'
import IsardDropdown from './shared/IsardDropdown.vue'
import IsardButton from './shared/IsardButton.vue'

export default {
  components: { IsardDropdown, IsardButton },
  props: {
    templates: {
      required: true,
      type: Array
    },
    desktops: {
      required: true,
      type: Array
    },
    gridView: {
      required: true,
      type: Boolean
    },
    persistent: {
      required: true,
      type: Boolean
    },
    status: {
      required: true,
      type: Object
    }
  },
  methods: {
    ...mapActions([
      'loadViewers',
      'openDesktop',
      'deleteDesktop',
      'changeDesktopStatus'
    ]),
    chooseDesktop (template) {
      const data = new FormData()
      data.append('template', template)
      this.$store.dispatch('createDesktop', data)
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
      table_fields: [
        {
          key: 'action',
          label: i18n.t('components.desktop-cards.table-header.action'),
          thStyle: { width: '7cm' }
        },
        {
          key: 'viewers',
          thStyle: { width: '8cm' },
          label: i18n.t('components.desktop-cards.table-header.viewers')
        },
        {
          key: 'ip',
          sortable: true,
          label: 'IP',
          thStyle: { width: '3cm' },
          tdClass: 'pt-3'
        },
        {
          key: 'state',
          sortable: true,
          formatter: value => {
            return value ? i18n.t(`views.select-template.status.${value.toLowerCase()}.text`) : ''
          },
          sortByFormatted: true,
          label: i18n.t('components.desktop-cards.table-header.state'),
          thStyle: { width: '3cm' },
          tdClass: 'pt-3'
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('components.desktop-cards.table-header.name'),
          thStyle: { width: '10cm' }
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('components.desktop-cards.table-header.description'),
          tdClass: 'pt-3'
        }
      ],
      ICONS: cardIcons
    }
  }
}
</script>

<style scoped>

  .persistent_desktop {
    min-height:250px !important;
    min-width:400px !important;
    z-index: 0 !important;
  }

  .temporal_desktop {
    min-height:100px !important;
    min-width:350px !important;
    z-index: 0 !important;
  }

  .card:hover{
    z-index: 1 !important;
    box-shadow: 8px 8px 5px blue;
    transform: scale(1.1);
  }

  .bounce-enter-active {
    animation: bounce-in .5s;
  }

  .bounce-leave-active {
    animation: bounce-in .5s reverse;
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

  @keyframes bounce-in {
    0% {
      transform: scale(0);
    }
    50% {
      transform: scale(1.5);
    }
    100% {
      transform: scale(1);
    }
  }
</style>
