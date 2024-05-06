<template>
  <b-container
    id="content"
    fluid
    class="scrollable-div-main"
  >
    <div v-if="storage_loaded && getStorage.length === 0">
      <h3><strong>{{ $t('views.storage.no-storage.title') }}</strong></h3>
      <p>{{ $t('views.storage.no-storage.subtitle') }}</p>
    </div>
    <IsardTable
      v-else
      :items="getStorage"
      :loading="!(storage_loaded)"
      :default-per-page="perPage"
      :page-options="pageOptions"
      :filter-on="filterOn"
      :fields="fields.filter(field => field.visible !== false)"
      class="px-5"
    >
      <template #cell(domains)="data">
        <span
          v-b-tooltip="{ title: data.item.id,
                         placement: 'right',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
        >
          {{ data.item.domains.map(entry => entry.name).join(', ') }}
        </span>
      </template>
      <template #cell(actualSize)="data">
        <p class="text-dark-gray m-0">
          {{ (data.item.actualSize / 1024 / 1024 / 1024).toFixed(1)+'GB' }}
        </p>
      </template>
      <template #cell(percentage)="data">
        <small
          v-if="userQuota.totalSize"
          class="h-25"
        >
          {{ ((data.item.actualSize / 1024 / 1024 / 1024) * 100 / userQuota.totalSize).toFixed(1) +'%' }}
        </small>
        <small v-else>
          0%
        </small>
        <QuotaProgressBar
          :value="(data.item.actualSize / 1024 / 1024 / 1024)"
          :max="userQuota.totalSize"
        />
      </template>
      <template #cell(last)="data">
        <p class="text-dark-gray m-0">
          {{ getDate(data.item.last) }}
        </p>
      </template>
      <template #cell(actions)="data">
        <b-button
          class="rounded-circle btn btn-blue px-2 mr-2"
          :title="$t('views.storage.buttons.increase.title')"
          @click="showIncreaseModal({ item: data.item, show: true })"
        >
          <b-icon
            icon="plus"
          />
        </b-button>
      </template>
    </IsardTable>
    <IncreaseModal />
  </b-container>
</template>

<script>
import IsardTable from '@/components/shared/IsardTable.vue'
import { mapGetters } from 'vuex'
import { ref, reactive, computed } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import i18n from '@/i18n'
import QuotaProgressBar from '@/components/profile/QuotaProgressBar.vue'
import IncreaseModal from '../components/storage/IncreaseModal.vue'

export default {
  components: {
    IsardTable,
    IncreaseModal,
    QuotaProgressBar
  },
  setup (props, context) {
    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const filterOn = reactive(['id', 'domains'])

    const $store = context.root.$store

    const userQuota = computed(() => $store.getters.getQuota)

    const getDate = (date) => {
      return DateUtils.dateAbsolute(date)
    }

    const fields = [
      {
        key: 'domains',
        sortable: true,
        label: i18n.t('views.storage.table-header.domains'),
        thStyle: { width: '20%' }
      },
      {
        key: 'actualSize',
        sortable: true,
        label: i18n.t('views.storage.table-header.actual-size'),
        thStyle: { width: '10%' }
      },
      {
        key: 'percentage',
        sortable: true,
        label: i18n.t('views.storage.table-header.percentage'),
        thStyle: { width: '10%' }
      },
      {
        key: 'last',
        sortable: true,
        label: i18n.t('views.storage.table-header.last'),
        thStyle: { width: '10%' }
      },
      {
        key: 'actions',
        label: i18n.t('views.storage.table-header.actions'),
        thStyle: { width: '1%' }
      }
    ]

    const showIncreaseModal = (data) => {
      $store.dispatch('showIncreaseModal', data)
    }

    return {
      perPage,
      pageOptions,
      filterOn,
      fields,
      userQuota,
      getDate,
      showIncreaseModal
    }
  },
  computed: {
    ...mapGetters(['getStorage', 'getUser', 'getQuota']),
    storage_loaded () {
      return this.$store.getters.getStorageLoaded
    }
  },
  created () {
    this.$store.dispatch('fetchStorage')
    this.$store.dispatch('fetchAppliedQuota')
  },
  destroyed () {
    this.$store.dispatch('resetStorageState')
  }
}
</script>
