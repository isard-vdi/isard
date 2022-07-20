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
        <b-row class="scrollable-div">
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-start"
          >
            <b-table
              :items="media"
              :fields="shared ? sharedFields : fields"
              tbody-tr-class="cursor-pointer"
              :responsive="true"
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
                  {{ data.item.status }}
                </p>
              </template>
              <template #cell(progressSize)="data">
                <p
                  v-if="data.item.status === 'Downloaded'"
                  class="text-dark-gray m-0"
                >
                  {{ data.item.progress.received }}
                </p>
              </template>
              <template #cell(actions)="data">
                <div class="d-flex justify-content-center align-items-center">
                  <b-button
                    v-if="data.item.editable"
                    class="rounded-circle px-2 mr-2 btn-dark-blue"
                    :title="$t('views.media.buttons.allowed.title')"
                    @click="showAllowedModal(data.item)"
                  >
                    <b-icon
                      icon="people-fill"
                      scale="0.75"
                    />
                  </b-button>
                </div>
              </template>
            </b-table>
          </b-col>
        </b-row>
      </b-skeleton-wrapper>
      <AllowedModal @updateAllowed="updateAllowed" />
    </b-container>
  </div>
</template>
<script>
import i18n from '@/i18n'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import { computed } from '@vue/composition-api'

export default {
  components: { ListItemSkeleton, AllowedModal },
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

    const mediaId = computed(() => $store.getters.getId)

    const showAllowedModal = (media) => {
      $store.dispatch('fetchAllowed', { table: 'media', id: media.id })
    }

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'media', id: mediaId.value, allowed: allowed })
    }

    const mediaIcon = (media) => {
      return media.kind === 'iso' ? 'compact-disc' : 'save'
    }

    return {
      showAllowedModal,
      updateAllowed,
      mediaIcon
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
          label: i18n.t('views.media.table-header.user'),
          thStyle: { width: '5%' }
        },
        {
          key: 'category',
          label: i18n.t('views.media.table-header.category'),
          thStyle: { width: '5%' }
        },
        {
          key: 'group',
          label: i18n.t('views.media.table-header.group'),
          thStyle: { width: '5%' }
        },
        {
          key: 'status',
          label: i18n.t('views.media.table-header.status'),
          thStyle: { width: '5%' }
        },
        {
          key: 'progressSize',
          label: i18n.t('views.media.table-header.progress-size'),
          thStyle: { width: '5%' }
        },
        {
          key: 'actions',
          label: i18n.t('views.media.table-header.actions'),
          thStyle: { width: '5%' }
        }
      ]
    }
  },
  destroyed () {
    this.$store.dispatch('resetMediaState')
  }
}
</script>
