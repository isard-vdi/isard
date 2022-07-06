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
              :fields="fields"
              tbody-tr-class="cursor-pointer"
              :responsive="true"
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
              <template #cell(actions)="data">
                <div class="d-flex justify-content-center align-items-center">
                  <b-button
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

    return {
      showAllowedModal,
      updateAllowed
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.media.table-header.name'),
          thStyle: { width: '25%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.media.table-header.description'),
          thStyle: { width: '35%' }
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
