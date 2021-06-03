<template>
 <b-table :items="desktops" :fields="tableConfig"
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
                v-if="data.item.state.toLowerCase() === desktopStates.stopped"
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
            <div v-if="showDropDown(data.item.state)">
                <isard-button
                  v-if="data.item.viewers.length === 1"
                  variant="primary"
                  :viewerName="data.item.viewers[0]"
                  :spinnerActive="waitingIp(data.item.state)"
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
                  :waitingIp="waitingIp(data.item.state)"
                  @dropdownClicked="openDesktop">
                </isard-dropdown>
            </div>
          </template>
          <template #cell(name)="data">
            <b-row>
              <font-awesome-icon :icon="data.item.icon" size="2x" class="mr-2"/>
              <b-col class="pt-1">
                <p>{{data.item.state ? templates.filter(template => template.id ===  data.item.template)[0].name : data.item.name}}</p>
              </b-col>
            </b-row>
          </template>
          <template #cell(state)="data">
            <div>
              {{data.item.state && $t(`views.select-template.status.${data.item.state.toLowerCase()}.text`)}}
              <b-spinner v-if="waitingIp(data.item.state)" small/>
            </div>
          </template>
        </b-table>
</template>

<script>
import i18n from '@/i18n'
import { mapActions } from 'vuex'
import IsardDropdown from '@/components/shared/IsardDropdown.vue'
import IsardButton from '@/components/shared/IsardButton.vue'
import { desktopStates, status } from '@/shared/constants'

import { DesktopConfig } from '@/shared/desktopConfig'

export default {
  components: { IsardDropdown, IsardButton },
  props: {
    desktops: {
      required: true,
      type: Array
    },
    templates: {
      required: true,
      type: Array
    }
  },
  methods: {
    ...mapActions([
      'openDesktop',
      'changeDesktopStatus',
      'deleteDesktop'
    ]),
    chooseDesktop (template) {
      const data = new FormData()
      data.append('template', template)
      this.$store.dispatch('createDesktop', data)
    },
    waitingIp (desktopState) {
      return desktopState && desktopState.toLowerCase() === desktopStates.waitingip
    },
    showDropDown (state) {
      return state && [desktopStates.started, desktopStates.waitingip].includes(state.toLowerCase())
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
      desktopStates,
      status,
      tableConfig: DesktopConfig.tableConfig
    }
  }
}
</script>
