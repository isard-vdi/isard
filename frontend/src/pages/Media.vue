<template>
  <b-container
    id="content"
    fluid
  >
    <b-tabs>
      <b-tab
        :active="currentTab === 'media'"
        @click="updateCurrentTab('media')"
      >
        <template #title>
          <b-spinner
            v-if="!(getMediaLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.media.tabs.media-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.media.tabs.media') }}</span>
        </template>
        <template v-if="getMediaLoaded && getMedia.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.media.no-media.title') }}</strong></h3>
            <p>{{ $t('views.media.no-media.subtitle') }}</p>
          </div>
        </template>
        <IsardTable
          v-else
          :items="getMedia"
          :loading="!(getMediaLoaded)"
          :page-options="pageOptions"
          :default-per-page="perPage"
          :filter-on="filterOn"
          :row-class="rowClass"
          :fields="fields.filter(field => field.visible !== false)"
          class="px-5 pt-3"
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
          <template #cell(description)="data">
            <p class="text-dark-gray m-0">
              {{ data.item.description }}
            </p>
          </template>
          <template #cell(status)="data">
            <b-tooltip
              v-if="data.item.status.toLowerCase() === 'downloadfailedinvalidformat'"
              :target="() => $refs['invalidTooltip']"
              :title="$t(`errors.media_invalid`)"
              triggers="hover"
              custom-class="isard-tooltip"
              show
            />
            <span
              v-if="data.item.status.toLowerCase() === 'downloadfailedinvalidformat'"
              ref="invalidTooltip"
            >
              <b-icon
                icon="exclamation-triangle-fill"
                variant="danger"
                class="danger-icon cursor-pointer"
              />
            </span>
            {{ $t(`views.media.status.${data.item.status.toLowerCase()}`) }}
          </template>
          <template #cell(progressSize)="data">
            <p
              v-if="['Downloaded', 'DownloadFailedInvalidFormat'].includes(data.item.status)"
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
          <template #cell(actions)="data">
            <div
              v-if="!['Downloading', 'maintenance'].includes(data.item.status)"
              class="d-flex align-items-center"
            >
              <b-button
                v-if="!['DownloadFailed', 'DownloadFailedInvalidFormat'].includes(data.item.status) && data.item.kind === 'iso'"
                class="rounded-circle px-2 mr-2 btn-green"
                :title="$t('views.media.buttons.new-desktop.title')"
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
                :title="$t('views.media.buttons.download.title')"
                @click="onClickDownloadMedia(data.item.id)"
              >
                <b-icon
                  icon="download"
                  scale="0.75"
                />
              </b-button>
              <b-button
                v-if="!['DownloadFailed', 'DownloadFailedInvalidFormat'].includes(data.item.status) && data.item.editable"
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
                v-if="data.item.editable"
                class="rounded-circle px-2 mr-2 btn-red"
                :title="$t('views.media.buttons.delete.title')"
                @click="showDeleteModal(data.item)"
              >
                <b-icon
                  icon="x"
                  scale="1"
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
        </IsardTable>
      </b-tab>
      <b-tab
        :active="currentTab === 'sharedMedia'"
        @click="updateCurrentTab('sharedMedia')"
      >
        <template #title>
          <b-spinner
            v-if="!(getSharedMediaLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.media.tabs.shared-media-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.media.tabs.shared-media') }}</span>
        </template>
        <template v-if="getSharedMediaLoaded && getSharedMedia.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.media.no-shared-media.title') }}</strong></h3>
            <p>{{ $t('views.media.no-shared-media.subtitle') }}</p>
          </div>
        </template>
        <IsardTable
          v-else
          :items="getSharedMedia"
          :loading="!(getSharedMediaLoaded)"
          :page-options="pageOptions"
          :default-per-page="perPage"
          :filter-on="filterOn"
          :row-class="rowClass"
          :fields="sharedFields.filter(field => field.visible !== false)"
          class="px-5 pt-3"
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
          <template #cell(description)="data">
            <p class="text-dark-gray m-0">
              {{ data.item.description }}
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
          <template #cell(status)="data">
            <b-tooltip
              v-if="data.item.status.toLowerCase() === 'downloadfailedinvalidformat'"
              :target="() => $refs['invalidTooltip']"
              :title="$t(`errors.media_invalid`)"
              triggers="hover"
              custom-class="isard-tooltip"
              show
            />
            <span
              v-if="data.item.status.toLowerCase() === 'downloadfailedinvalidformat'"
              ref="invalidTooltip"
            >
              <b-icon
                icon="exclamation-triangle-fill"
                variant="danger"
                class="danger-icon cursor-pointer"
              />
            </span>
            {{ $t(`views.media.status.${data.item.status.toLowerCase()}`) }}
          </template>
          <template #cell(progressSize)="data">
            <p
              v-if="['Downloaded', 'DownloadFailedInvalidFormat'].includes(data.item.status)"
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
          <template #cell(actions)="data">
            <div
              v-if="!['Downloading', 'maintenance'].includes(data.item.status)"
              class="d-flex align-items-center"
            >
              <b-button
                v-if="!['DownloadFailed', 'DownloadFailedInvalidFormat'].includes(data.item.status) && data.item.kind === 'iso'"
                class="rounded-circle px-2 mr-2 btn-green"
                :title="$t('views.media.buttons.new-desktop.title')"
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
                :title="$t('views.media.buttons.download.title')"
                @click="onClickDownloadMedia(data.item.id)"
              >
                <b-icon
                  icon="download"
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
        </IsardTable>
      </b-tab>
      <AllowedModal @updateAllowed="updateAllowed" />
      <DeleteMediaModal @deleteMedia="deleteMedia" />
    </b-tabs>
  </b-container>
</template>
<script>
import IsardTable from '@/components/shared/IsardTable.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import DeleteMediaModal from '@/components/media/DeleteMediaModal.vue'
import { mapGetters, mapActions } from 'vuex'
import { computed, ref, reactive } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  components: {
    IsardTable,
    AllowedModal,
    DeleteMediaModal
  },
  setup (_, context) {
    const perPage = ref(5)
    const pageOptions = ref([5, 10, 20, 30, 50, 100])

    const $store = context.root.$store
    $store.dispatch('fetchMedia')
    $store.dispatch('fetchSharedMedia')

    const allowedId = computed(() => $store.getters.getId)

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'media', id: allowedId.value, allowed: allowed })
    }

    const currentTab = computed(() => $store.getters.getCurrentTab)
    const mediaId = computed(() => $store.getters.getMediaId)

    const deleteMedia = () => {
      $store.dispatch('deleteMedia', mediaId.value)
    }

    const filterOn = reactive(['name', 'description'])
    const rowClass = 'cursor-pointer'

    const fields = [
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
    ]

    const sharedFields = [
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

    const showAllowedModal = (media) => {
      $store.dispatch('fetchAllowed', { table: 'media', id: media.id })
    }

    const mediaIcon = (media) => {
      return media.kind === 'iso' ? 'compact-disc' : 'save'
    }

    const showDeleteModal = (media) => {
      $store.dispatch('fetchMediaDesktops', { mediaId: media.id, name: media.name })
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

    return {
      perPage,
      pageOptions,
      currentTab,
      updateAllowed,
      deleteMedia,
      filterOn,
      rowClass,
      fields,
      sharedFields,
      showAllowedModal,
      mediaIcon,
      showDeleteModal,
      onClickGoToNewFromMedia,
      onClickDownloadMedia,
      onClickStopDownload
    }
  },
  computed: {
    ...mapGetters([
      'getMedia',
      'getMediaLoaded',
      'getSharedMedia',
      'getSharedMediaLoaded'
    ])
  },
  destroyed () {
    this.$store.dispatch('resetMediaState')
  },
  methods: {
    ...mapActions([
      'updateCurrentTab'
    ])
  }
}
</script>
