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
            <list-item-skeleton class="mb-2" />)
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
                aria-controls="storage-table"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>
        <b-row>
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-start"
          >
            <b-table
              id="storage-table"
              :items="storage"
              :fields="fields"
              :responsive="true"
              :per-page="perPage"
              :current-page="currentPage"
              :filter="filter"
              :filter-included-fields="filterOn"
              @filtered="onFiltered"
            >
              <template #cell(id)="data">
                <p class="m-0 font-weight-bold">
                  {{ data.item.id }}
                </p>
              </template>
              <template #cell(domains)="data">
                <span>
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
                  aria-controls="template-table"
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
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import QuotaProgressBar from '@/components/profile/QuotaProgressBar.vue'
import { ref, reactive, watch, computed } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'

export default {
  components: { ListItemSkeleton, QuotaProgressBar },
  props: {
    storage: {
      required: true,
      type: Array
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
    const totalRows = ref(1)
    const filter = ref('')
    const filterOn = reactive(['id', 'domains'])

    const $store = context.root.$store

    const userQuota = computed(() => $store.getters.getQuota)

    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const getDate = (date) => {
      return DateUtils.dateAbsolute(date)
    }

    watch(() => props.storage, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })
    return {
      onFiltered,
      filter,
      filterOn,
      perPage,
      currentPage,
      totalRows,
      pageOptions,
      getDate,
      userQuota
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'id',
          label: 'ID',
          thStyle: { width: '30%' }
        },
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
        }
      ]
    }
  }
}

</script>
