<template>
  <b-table :items="desktops" :fields="tableConfig"
        id="desktops-table" class="text-left" key="desktops_table" responsive>
          <template #cell(action)="data">
              <b-button v-if="['started','stopped','waitingip'].includes(data.item.state.toLowerCase())" :variant="status[data.item.state.toLowerCase()].variant"
              @click="changeDesktopStatus({action: status[data.item.state.toLowerCase()].action, desktopId: data.item.id})">
                <font-awesome-icon :icon="status[data.item.state.toLowerCase()].icon" class="mr-2"/>
                {{$t(`views.select-template.status.${data.item.state.toLowerCase()}.action`)}}
              </b-button>
          </template>
          <template #cell(viewers)="data">
            <div v-if="showDropDown(data.item.state)">
              <isard-button
                v-if="data.item.viewers.length === 1"
                variant="primary"
                :viewerName="data.item.viewers[0]"
                :spinnerActive="waitingIp(data.item.state)"
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
                :waitingIp="waitingIp(data.item.state)"
                @dropdownClicked="openDesktop">
              </isard-dropdown>
            </div>
          </template>
          <template #cell(name)="data">
            <b-row>
              <font-awesome-icon :icon="data.item.icon" size="2x" class="mr-2"/>
              <b-col class="pt-1">
                <p>{{ data.item.name }}</p>
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
    }
  },
  methods: {
    ...mapActions([
      'openDesktop',
      'changeDesktopStatus'
    ]),
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
