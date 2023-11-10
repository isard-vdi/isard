<template>
  <div class="table-list px-5 table-scrollable-div">
    <b-container
      fluid
      class="px-0"
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
        <!-- Filter -->
        <b-row class="mt-2">
          <b-col
            cols="8"
            md="6"
            lg="4"
            xl="4"
          >
            <b-input-group size="sm">
              <b-form-input
                id="filter-input"
                v-model="filter"
                type="search"
                :placeholder="$t('forms.filter-placeholder')"
              />
              <b-input-group-append>
                <b-button
                  :disabled="!filter"
                  @click="filter = ''"
                >
                  {{ $t('forms.clear') }}
                </b-button>
              </b-input-group-append>
            </b-input-group>
          </b-col>
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
                aria-controls="deployment-desktops-table"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>

        <b-row>
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-start4"
          >
            <b-table
              id="deployment-desktops-table"
              :items="desktops"
              :fields="fields"
              :responsive="true"
              :per-page="perPage"
              :current-page="currentPage"
              :filter="filter"
              :filter-included-fields="filterOn"
              @filtered="onFiltered"
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
                <!-- Main action button persistent-->
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
              <template #cell(delete)="data">
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
              </template>
            </b-table>
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
                  aria-controls="deployment-desktops-table"
                  size="sm"
                />
              </b-col>
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
import { onUnmounted, ref, reactive, watch } from '@vue/composition-api'
import { ErrorUtils } from '@/utils/errorUtils'
import { DateUtils } from '@/utils/dateUtils'

export default {
  components: { DesktopButton, IsardDropdown, ListItemSkeleton },
  props: {
    listTitle: String,
    visible: {
      required: true,
      type: Boolean,
      default: false
    },
    desktops: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    }
  },
  setup (props, context) {
    const $store = context.root.$store
    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const currentPage = ref(1)
    const totalRows = ref(1)
    const filter = ref('')
    const filterOn = reactive(['userName', 'groupName'])

    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const getDate = (date) => {
      return DateUtils.dateAbsolute(date)
    }

    watch(() => props.desktops, (newVal) => {
      totalRows.value = newVal.length
    })

    onUnmounted(() => {
      $store.dispatch('resetDeploymentState')
    })

    const canStart = (desktop) => {
      if (desktop.needsBooking) {
        return desktop.bookingId
      } else {
        return true
      }
    }

    return {
      onFiltered,
      filter,
      filterOn,
      perPage,
      pageOptions,
      currentPage,
      totalRows,
      getDate,
      canStart
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
          key: 'delete',
          label: '',
          thStyle: { width: '5%' }
        }
      ]
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
  destroyed () {
    this.$snotify.clear()
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

<style scoped>
.table-scrollable-div {
  height: calc(100vh - 300px);
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
