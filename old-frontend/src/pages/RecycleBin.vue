<template>
  <b-container
    id="content"
    fluid
    class="px-5 scrollable-div-main"
  >
    <b-skeleton-wrapper
      :loading="!recycleBinLoaded"
    >
      <template #loading>
        <RecycleBinSkeleton />
      </template>
      <h3 class="mb-4">
        <strong>
          {{ $t(`views.recycle-bin.title.${recycleBin.itemType}`, { name: recycleBin.itemName, date: dateAbsolute(recycleBin.accessed) }) }}
          <span class="text-secondary">({{ recycleBin.size }})</span>
        </strong>
      </h3>
      <div v-if="recycleBin.templates.length">
        <h4 class="font-weight-bold mb-4">
          <font-awesome-icon
            :icon="['fas', 'cubes']"
            class="mr-1 d-xl-inline"
          />
          {{ $t('views.recycle-bin.templates.title') }}
        </h4>
        <IsardTable
          :items="recycleBin.templates"
          :loading="!recycleBinLoaded"
          :default-per-page="perPage"
          :page-options="pageOptions"
          :filter-on="templatesFilterOn"
          :fields="templatesFields.filter(field => field.visible !== false)"
        />
      </div>
      <div v-if="recycleBin.deployments.length">
        <hr v-if="recycleBin.templates.length">
        <h4 class="font-weight-bold mb-4">
          <b-iconstack
            class="pt-1 d-xl-inline"
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
          {{ $t('views.recycle-bin.deployments.title') }}
        </h4>
        <IsardTable
          :items="recycleBin.deployments"
          :loading="!recycleBinLoaded"
          :default-per-page="perPage"
          :page-options="pageOptions"
          :filter-on="deploymentsFilterOn"
          :fields="deploymentsFields.filter(field => field.visible !== false)"
        />
      </div>
      <div v-if="recycleBin.desktops.length">
        <hr v-if="recycleBin.deployments.length">
        <h4 class="font-weight-bold mb-4">
          <font-awesome-icon
            :icon="['fas', 'desktop']"
            class="mr-1 d-xl-inline"
          />
          {{ $t('views.recycle-bin.desktops.title') }}
        </h4>
        <IsardTable
          :items="recycleBin.desktops"
          :loading="!recycleBinLoaded"
          :default-per-page="perPage"
          :page-options="pageOptions"
          :filter-on="desktopsFilterOn"
          :fields="desktopsFields.filter(field => field.visible !== false)"
        />
      </div>
      <div v-if="recycleBin.storages.length">
        <hr>
        <h4 class="font-weight-bold mb-4">
          <b-icon
            icon="folder-fill"
          />
          {{ $t('views.recycle-bin.storages.title') }}
        </h4>
        <IsardTable
          :items="recycleBin.storages"
          :loading="!recycleBinLoaded"
          :default-per-page="perPage"
          :page-options="pageOptions"
          :filter-on="storagesFilterOn"
          :fields="storagesFields.filter(field => field.visible !== false)"
        />
      </div>
    </b-skeleton-wrapper>
  </b-container>
</template>
<script>
import i18n from '@/i18n'
import { computed, onMounted, ref, reactive } from '@vue/composition-api'
import IsardTable from '@/components/shared/IsardTable.vue'
import RecycleBinSkeleton from '@/components/recycleBin/RecycleBinSkeleton.vue'
import { DateUtils } from '@/utils/dateUtils'

export default {
  components: {
    IsardTable,
    RecycleBinSkeleton
  },
  setup (props, context) {
    const perPage = ref(5)
    const pageOptions = ref([5, 10, 20, 30, 50, 100])
    const $store = context.root.$store

    onMounted(() => {
      $store.dispatch('fetchRecycleBin', { id: context.root.$route.params.id })
    })

    const recycleBin = computed(() => $store.getters.getRecycleBin)
    const recycleBinLoaded = computed(() => $store.getters.getRecycleBinLoaded)

    // Desktops
    const desktopsFilterOn = reactive(['id', 'name', 'user', 'category', 'group'])
    const desktopsFields = [
      {
        key: 'id',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.id'),
        visible: false
      },
      {
        key: 'name',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.name')
      },
      {
        key: 'username',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.user')
      },
      {
        key: 'category',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.category')
      },
      {
        key: 'group',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.group')
      },
      {
        key: 'accessed',
        sortable: true,
        label: i18n.t('views.recycle-bin.desktops.table-header.accessed'),
        formatter: (value, key, item) => {
          return DateUtils.dateAbsolute(item.accessed)
        }
      }
    ]

    // Templates
    const templatesFilterOn = reactive(['id', 'name', 'user', 'category', 'group'])
    const templatesFields = [
      {
        key: 'id',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.id'),
        visible: false
      },
      {
        key: 'name',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.name')
      },
      {
        key: 'username',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.user')
      },
      {
        key: 'category',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.category')
      },
      {
        key: 'group',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.group')
      },
      {
        key: 'accessed',
        sortable: true,
        label: i18n.t('views.recycle-bin.templates.table-header.accessed'),
        formatter: (value, key, item) => {
          return DateUtils.dateAbsolute(item.accessed)
        }
      }
    ]

    // Deployments
    const deploymentsFilterOn = reactive(['id', 'name', 'user', 'category', 'group'])
    const deploymentsFields = [
      {
        key: 'id',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.id'),
        visible: false
      },
      {
        key: 'name',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.name')
      },
      {
        key: 'desktopName',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.desktop-name')
      },
      {
        key: 'user',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.user')
      },
      {
        key: 'category',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.category')
      },
      {
        key: 'group',
        sortable: true,
        label: i18n.t('views.recycle-bin.deployments.table-header.group')
      }
    ]

    // Storages
    const storagesFilterOn = reactive(['path', 'status', 'format', 'size', 'used', 'parent', 'user', 'category', 'domains'])
    const storagesFields = [
      {
        key: 'id',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.id')
      },
      {
        key: 'path',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.path')
      },
      {
        key: 'status',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.status')
      },
      {
        key: 'format',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.format')
      },
      {
        key: 'size',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.size')
      },
      {
        key: 'used',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.used')
      },
      {
        key: 'parent',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.parent')
      },
      {
        key: 'user',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.user')
      },
      {
        key: 'category',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.category')
      },
      {
        key: 'domains',
        sortable: true,
        label: i18n.t('views.recycle-bin.storages.table-header.domains'),
        formatter: (value, key, item) => {
          return item.domains.join(', ')
        }
      }
    ]

    const dateAbsolute = (date) => {
      return DateUtils.dateAbsolute(date)
    }

    return {
      recycleBin,
      perPage,
      pageOptions,
      recycleBinLoaded,
      desktopsFilterOn,
      desktopsFields,
      templatesFilterOn,
      templatesFields,
      storagesFilterOn,
      storagesFields,
      deploymentsFilterOn,
      deploymentsFields,
      dateAbsolute
    }
  }
}
</script>
