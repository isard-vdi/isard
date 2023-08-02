<template>
  <div class="table-list px-5">
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
            <list-item-skeleton class="mb-2" />
          </b-col>
        </template>
        <!-- Filter -->
        <b-row class="mt-4">
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
                aria-controls="template-table"
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
              id="media-table"
              :items="media"
              :fields="shared ? sharedFields : fields"
              tbody-tr-class="cursor-pointer"
              :responsive="true"
              :per-page="perPage"
              :current-page="currentPage"
              :filter="filter"
              :filter-included-fields="filterOn"
              @filtered="onFiltered"
            >
              <template #cell(name)="data">
                <p class="m-0 font-weight-bold">
                  <font-awesome-icon
                    class="mr-2"
                    :icon="mediaIcon(data.item)"
                  />
                  {{ data.item.name }}
                </p>
              </template>
              <template #cell(user)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.userName }}
                </p>
              </template>
              <template #cell(category)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.categoryName }}
                </p>
              </template>
              <template #cell(group)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.groupName }}
                </p>
              </template>
              <template #cell(description)="data">
                <p class="text-dark-gray m-0">
                  {{ data.item.description }}
                </p>
              </template>
              <template #cell(status)="data">
                <p class="text-dark-gray m-0">
                  {{ $t(`views.media.status.${data.item.status.toLowerCase()}`) }}
                </p>
              </template>
              <template #cell(progressSize)="data">
                <p
                  v-if="data.item.status === 'Downloaded'"
                  class="text-dark-gray m-0"
                >
                  {{ data.item.progress.received }}
                </p>
                <div v-else-if="data.item.status !== 'DownloadFailed'">
                  <b-progress
                    :max="100"
                    height="2rem"
                  >
                    <b-progress-bar
                      variant="info"
                      :value="data.item.progress.total_percent"
                      show-progress
                      animated
                    >
                      <strong>{{ data.item.progress.total_percent }} %</strong>
                    </b-progress-bar>
                  </b-progress>
                </div>
              </template>
              <template
                #cell(actions)="data"
              >
                <div
                  v-if="!['Downloading', 'maintenance'].includes(data.item.status)"
                  class="d-flex align-items-center"
                >
                  <b-button
                    v-if="data.item.status !== 'DownloadFailed' && data.item.kind === 'iso'"
                    class="rounded-circle px-2 mr-2 btn-green"
                    :title="$t('views.media.buttons.new-desktop')"
                    @click="onClickGoToNewFromMedia(data.item)"
                  >
                    <b-icon
                      icon="tv"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="data.item.status === 'DownloadFailed'"
                    class="rounded-circle px-2 mr-2 btn-blue"
                    :title="$t('views.media.buttons.download')"
                    @click="onClickDownloadMedia(data.item.id)"
                  >
                    <b-icon
                      icon="download"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="!shared && data.item.status !== 'DownloadFailed' && data.item.editable"
                    class="rounded-circle px-2 mr-2 btn-dark-blue"
                    :title="$t('views.media.buttons.allowed.title')"
                    @click="showAllowedModal(data.item)"
                  >
                    <b-icon
                      icon="people-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    v-if="!shared && data.item.editable"
                    class="rounded-circle px-2 mr-2 btn-red"
                    :title="$t('views.media.buttons.delete.title')"
                    @click="showDeleteModal(data.item)"
                  >
                    <b-icon
                      icon="trash-fill"
                      scale="0.75"
                    />
                  </b-button>
                </div>
                <b-button
                  v-else-if="data.item.status !== 'maintenance'"
                  class="rounded-circle px-2 mr-2 btn-red"
                  :title="$t('views.media.buttons.stop-download.title')"
                  @click="onClickStopDownload(data.item.id)"
                >
                  <b-icon
                    icon="stop"
                    scale="0.75"
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
                  aria-controls="media-table"
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
import { ref, reactive, watch } from '@vue/composition-api'

export default {
  components: { ListItemSkeleton },
  props: {
    media: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    },
    shared: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  setup (props, context) {
    const $store = context.root.$store

    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const currentPage = ref(1)
    const totalRows = ref(1)
    const filter = ref('')
    const filterOn = reactive(['name', 'description'])

    const showAllowedModal = (media) => {
      $store.dispatch('fetchAllowed', { table: 'media', id: media.id })
    }

    const mediaIcon = (media) => {
      return media.kind === 'iso' ? 'compact-disc' : 'save'
    }

    const showDeleteModal = (media) => {
      $store.dispatch('fetchMediaDesktops', { mediaId: media.id, name: media.name })
    }

    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const onClickGoToNewFromMedia = (media) => {
      $store.dispatch('goToNewFromMedia', media)
    }

    const onClickDownloadMedia = (mediaId) => {
      $store.dispatch('downloadMedia', mediaId)
    }

    const onClickStopDownload = (mediaId) => {
      $store.dispatch('stopMediaDownload', mediaId)
    }

    watch(() => props.media, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })

    return {
      showAllowedModal,
      mediaIcon,
      showDeleteModal,
      onFiltered,
      filter,
      filterOn,
      perPage,
      pageOptions,
      currentPage,
      totalRows,
      onClickGoToNewFromMedia,
      onClickDownloadMedia,
      onClickStopDownload
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.media.table-header.name'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.media.table-header.description'),
          thStyle: { width: '20%' }
        },
        {
          key: 'status',
          sortable: true,
          label: i18n.t('views.media.table-header.status'),
          thStyle: { width: '5%' }
        },
        {
          key: 'progressSize',
          label: i18n.t('views.media.table-header.progress-size'),
          thStyle: { width: '10%' }
        },
        {
          key: 'actions',
          label: i18n.t('views.media.table-header.actions'),
          thStyle: { width: '5%' }
        }
      ],
      sharedFields: [
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.media.table-header.name'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.media.table-header.description'),
          thStyle: { width: '20%' }
        },
        {
          key: 'user',
          sortable: true,
          label: i18n.t('views.media.table-header.user'),
          thStyle: { width: '5%' }
        },
        {
          key: 'category',
          sortable: true,
          label: i18n.t('views.media.table-header.category'),
          thStyle: { width: '5%' }
        },
        {
          key: 'group',
          sortable: true,
          label: i18n.t('views.media.table-header.group'),
          thStyle: { width: '5%' }
        },
        {
          key: 'status',
          sortable: true,
          label: i18n.t('views.media.table-header.status'),
          thStyle: { width: '5%' }
        },
        {
          key: 'progressSize',
          label: i18n.t('views.media.table-header.progress-size'),
          thStyle: { width: '10%' }
        },
        {
          key: 'actions',
          label: i18n.t('views.media.table-header.actions'),
          thStyle: { width: '5%' }
        }
      ]
    }
  }
}
</script>
