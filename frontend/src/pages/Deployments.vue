<template>
  <b-container
    id="content"
    fluid
  >
    <div v-if="deployments_loaded && getDeployments.length === 0">
      <h3><strong>{{ $t('views.deployments.no-deployments.title') }}</strong></h3>
      <p>{{ $t('views.deployments.no-deployments.subtitle') }}</p>
    </div>
    <IsardTable
      v-else
      :items="sortedDeployments"
      :loading="!(deployments_loaded)"
      :default-per-page="perPage"
      :page-options="pageOptions"
      :filter-on="filterOn"
      :fields="fields.filter(field => field.visible !== false)"
      :row-class="rowClass"
      class="px-5 table-scrollable-div"
      @rowClicked="redirectDeployment"
    >
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
      <template #cell(startedDesktops)="data">
        <p class="text-dark-gray m-0">
          {{ data.item.startedDesktops }}
        </p>
      </template>
      <template #cell(visibleDesktops)="data">
        <p class="text-dark-gray m-0">
          {{ data.item.visibleDesktops }}
        </p>
      </template>
      <template #cell(totalDesktops)="data">
        <p class="text-dark-gray m-0">
          {{ data.item.totalDesktops }}
        </p>
      </template>
      <template #cell(actions)="data">
        <div class="d-flex align-items-center">
          <b-button
            class="rounded-circle px-2 mr-2 btn-green"
            :title="$t('components.statusbar.deployment.buttons.co-owners.title')"
            @click="showOwnersModal(data.item)"
          >
            <b-icon
              icon="person-fill"
              scale="0.75"
            />
          </b-button>
          <b-button
            class="rounded-circle btn btn-blue px-2 mr-2"
            :title="$t('components.statusbar.deployment.buttons.edit.title')"
            @click="editDeployment(data.item.id)"
          >
            <b-icon
              icon="pencil-fill"
              scale="0.75"
            />
          </b-button>
          <b-button
            class="rounded-circle px-2 mr-2 btn-dark-blue"
            :title="$t('components.statusbar.deployment.buttons.allowed.title')"
            @click="showAllowedModal(data.item.id)"
          >
            <b-icon
              icon="people-fill"
              scale="0.75"
            />
          </b-button>
          <b-button
            class="rounded-circle btn btn-red px-2 mr-2"
            :title="$t('components.statusbar.deployment.buttons.delete.title')"
            @click="deleteDeployment(data.item)"
          >
            <b-icon
              icon="x"
              scale="1"
            />
          </b-button>
          <b-button
            v-if="data.item.needsBooking"
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
    </IsardTable>
    <AllowedModal @updateAllowed="updateUsers" />
  </b-container>
</template>
<script>
// @ is an alias to /src
import IsardTable from '@/components/shared/IsardTable.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import { mapGetters } from 'vuex'
import { ref, reactive, computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  components: {
    IsardTable,
    AllowedModal
  },
  setup (props, context) {
    const $store = context.root.$store

    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const filterOn = reactive(['name', 'description', 'desktopName', 'template'])

    const rowClass = (item, type) => {
      if (item && type === 'row') {
        if (item.visibleDesktops > 0) {
          return 'cursor-pointer visibleHighlight'
        } else {
          return 'cursor-pointer'
        }
      } else {
        return null
      }
    }

    const showAllowedModal = (deploymentId) => {
      $store.dispatch('fetchAllowed', { table: 'deployments', id: deploymentId })
    }

    const deploymentId = computed(() => $store.getters.getId)

    const updateUsers = (allowed) => {
      $store.dispatch('editDeploymentUsers', { id: deploymentId.value, allowed: allowed })
    }

    const editDeployment = (deploymentId) => {
      $store.dispatch('goToEditDeployment', deploymentId)
    }

    const redirectDeployment = (item) => {
      context.root.$router.push({ name: 'deployment_desktops', params: { id: item.id } })
    }

    const deleteDeployment = (deployment) => {
      $store.dispatch('updateDeploymentModal', {
        show: true,
        type: 'delete',
        color: 'red',
        item: { id: deployment.id, name: deployment.name }
      })
    }

    const onClickBookingDesktop = (deployment) => {
      const data = { id: deployment.id, type: 'deployment', name: deployment.name }
      $store.dispatch('goToItemBooking', data)
    }

    const showOwnersModal = (deployment) => {
      $store.dispatch('fetchCoOwners', deployment.id)
      $store.dispatch('updateDeploymentModal', {
        show: true,
        type: 'coOwners',
        color: 'green',
        item: { id: deployment.id, name: deployment.name }
      })
    }

    const fields = [
      {
        key: 'name',
        sortable: true,
        label: i18n.t('views.deployments.table-header.name'),
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'description',
        sortable: true,
        label: i18n.t('views.deployments.table-header.description'),
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'desktopName',
        sortable: true,
        label: i18n.t('views.deployments.table-header.desktop-name'),
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'template',
        sortable: true,
        label: i18n.t('views.deployments.table-header.template'),
        thStyle: { width: '20%' },
        tdClass: 'name'
      },
      {
        key: 'startedDesktops',
        sortable: true,
        label: i18n.t('views.deployments.table-header.started-desktops'),
        thStyle: { width: '5%' }
      },
      {
        key: 'visibleDesktops',
        sortable: true,
        label: i18n.t('views.deployments.table-header.visible-desktops'),
        thStyle: { width: '5%' }
      },
      {
        key: 'totalDesktops',
        sortable: true,
        label: i18n.t('views.deployments.table-header.total-desktops'),
        thStyle: { width: '5%' }
      },
      {
        key: 'actions',
        label: i18n.t('views.deployments.table-header.actions'),
        thStyle: { width: '5%' }
      }
    ]

    return {
      perPage,
      pageOptions,
      filterOn,
      rowClass,
      showAllowedModal,
      updateUsers,
      editDeployment,
      redirectDeployment,
      deleteDeployment,
      onClickBookingDesktop,
      showOwnersModal,
      fields
    }
  },
  computed: {
    ...mapGetters(['getDeployments']),
    sortedDeployments () {
      return this.getDeployments.slice().sort(d => {
        // return visible deployments first
        return d.visible ? -1 : 1
      })
    },
    deployments_loaded () {
      return this.$store.getters.getDeploymentsLoaded
    }
  },
  created () {
    this.$store.dispatch('fetchDeployments')
  },
  destroyed () {
    this.$store.dispatch('resetDeploymentsState')
  }
}
</script>
