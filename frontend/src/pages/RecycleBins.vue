<template>
  <b-container
    id="content"
    fluid
    class="px-5 scrollable-div-main"
  >
    <h2 class="mb-4">
      <strong>
        <b-icon
          icon="trash"
        />
        {{ $t('views.recycle-bins.title') }}
      </strong>
    </h2>
    <RecycleBinModal />
    <div v-if="recycleBinsLoaded && recycleBins.length == 0">
      <b-row
        class="d-flex justify-content-center align-items-center"
        align-v="center"
      >
        <b-col
          cols="3"
        />
        <b-col
          cols="6"
          class="text-center"
        >
          <b-row
            class="justify-content-center"
            style="height: 8rem"
          />
          <font-awesome-icon
            :icon="['fas', 'recycle']"
            class="mb-4 fa-10x"
          />
          <h3><strong>{{ $t('views.recycle-bins.no-recycle-bin.title') }}</strong></h3>
          <p
            v-if="maxTime === 0"
          >
            {{ $t("components.statusbar.recycle-bins.immediately") }}
          </p><p
            v-else-if="maxTime !== 'null'"
          >
            {{ $t('views.recycle-bins.no-recycle-bin.subtitle', { time: maxTime }) }}
          </p>
        </b-col>
        <b-col
          cols="3"
        />
      </b-row>
    </div>
    <IsardTable
      v-else
      :items="recycleBins"
      :loading="!(recycleBinsLoaded)"
      :default-per-page="perPage"
      :page-options="pageOptions"
      :filter-on="filterOn"
      :fields="fields.filter(field => field.visible !== false)"
      :row-class="rowClass"
      @rowClicked="redirectRecycleBin"
    >
      <template #cell(itemType)="data">
        <b-iconstack
          v-if="data.item.itemType == 'bulk'"
          class="mr-1 d-xl-inline"
        >
          <b-icon
            stacked
            icon="tv"
            shift-v="4"
            shift-h="-4"
          />
          <b-icon
            stacked
            icon="tv-fill"
          />
          <b-icon
            stacked
            variant="danger"
            icon="x"
            scale="2"
          />
        </b-iconstack>
        <font-awesome-icon
          v-if="data.item.itemType == 'template'"
          :icon="['fas', 'cubes']"
          class="mr-1 d-xl-inline"
        />
        <b-iconstack
          v-else-if="data.item.itemType == 'deployment'"
          class="mr-1 d-xl-inline"
        >
          <b-icon
            stacked
            icon="tv"
            shift-v="4"
            shift-h="-4"
          />
          <b-icon
            stacked
            icon="tv-fill"
          />
        </b-iconstack>
        <font-awesome-icon
          v-else-if="data.item.itemType == 'desktop'"
          :icon="['fas', 'desktop']"
          class="mr-1 d-xl-inline"
        />
        <b-icon
          v-if="data.item.itemType == 'user'"
          icon="person-fill"
          class="mr-1 d-xl-inline"
        />
        {{ $t(`views.recycle-bins.item-type.${data.item.itemType}`) }}
      </template>
      <template #cell(actions)="data">
        <b-button
          class="rounded-circle btn-blue px-2 mr-2"
          :title="$t('components.statusbar.recycle-bin.buttons.info.title')"
          @click="redirectRecycleBin(data.item)"
        >
          <b-icon
            icon="info"
            scale="1"
          />
        </b-button>
        <span>
          <b-button
            class="rounded-circle btn-green px-2 mr-2"
            :title="$t('components.statusbar.recycle-bin.buttons.restore.title')"
            @click="restoreRecycleBin(data.item.id)"
          >
            <b-icon
              icon="arrow-clockwise"
              scale="0.75"
            />
          </b-button>
          <b-button
            class="rounded-circle btn-red px-2 mr-2"
            :title="$t('components.statusbar.recycle-bin.buttons.delete.title')"
            @click="deleteRecycleBin(data.item.id)"
          >
            <b-icon
              icon="x"
              scale="1"
            />
          </b-button>
        </span>
      </template>
    </IsardTable>
  </b-container>
</template>

<script>
import { computed, onMounted, ref, reactive } from '@vue/composition-api'
import IsardTable from '@/components/shared/IsardTable.vue'
import RecycleBinModal from '@/components/recycleBin/RecycleBinModal.vue'
import i18n from '@/i18n'
import { DateUtils } from '@/utils/dateUtils'

export default {
  components: {
    IsardTable,
    RecycleBinModal
  },
  setup (props, context) {
    const $store = context.root.$store

    onMounted(() => {
      $store.dispatch('fetchRecycleBins')
      $store.dispatch('fetchMaxTime')
    })

    const user = computed(() => $store.getters.getUser)
    const recycleBins = computed(() => $store.getters.getRecycleBins)
    const recycleBinsLoaded = computed(() => $store.getters.getRecycleBinsLoaded)
    const maxTime = computed(() => $store.getters.getMaxTime.time)

    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const filterOn = reactive(['id', 'itemName', 'agentName', 'status', 'desktops', 'templates', 'deployments', 'accessed'])
    const rowClass = 'cursor-pointer'

    const redirectRecycleBin = (item) => {
      context.root.$router.push({ name: 'recycleBin', params: { id: item.id } })
    }

    const fields = [
      {
        key: 'itemType',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.type')
      },
      {
        key: 'id',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.id'),
        visible: false
      },
      {
        key: 'size',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.size')
      },
      {
        key: 'itemName',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.name')
      },
      {
        key: 'agentName',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.agent-name')
      },
      {
        key: 'status',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.status'),
        formatter: (value, key, item) => {
          return i18n.t(`views.recycle-bins.status.${item.status}`)
        }
      },
      {
        key: 'desktops',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.desktops')
      },
      {
        key: 'templates',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.templates'),
        thStyle: { width: '10%' }
      },
      {
        key: 'deployments',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.deployments')
      },
      {
        key: 'accessed',
        sortable: true,
        label: i18n.t('views.recycle-bins.table-header.accessed'),
        formatter: (value, key, item) => {
          return DateUtils.dateAbsolute(item.accessed)
        }
      },
      {
        key: 'actions',
        label: i18n.t('views.recycle-bins.table-header.actions')
      }
    ]

    // Recycle Bin
    const restoreRecycleBin = (id) => {
      $store.dispatch('updateRecycleBinModal', {
        show: true,
        type: 'restore',
        item: {
          id: id
        }
      })
    }

    const deleteRecycleBin = (id) => {
      $store.dispatch('updateRecycleBinModal', {
        show: true,
        type: 'delete',
        item: {
          id: id
        }
      })
    }

    return {
      recycleBins,
      recycleBinsLoaded,
      filterOn,
      perPage,
      pageOptions,
      redirectRecycleBin,
      rowClass,
      fields,
      restoreRecycleBin,
      deleteRecycleBin,
      user,
      DateUtils,
      maxTime
    }
  }
}
</script>
<style scoped>
#app {
  background-color: red !important
}
</style>
