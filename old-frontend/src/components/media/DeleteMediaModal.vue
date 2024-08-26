<template>
  <b-modal
    id="deleteMediaModal"
    v-model="showDeleteMediaModal"
    size="xl"
    :title="$t(`views.media.delete-media.title`)"
    centered
    @hidden="closeDeleteMediaModal"
  >
    <div class="ml-4 mr-4">
      <b-icon
        class="mr-2"
        variant="danger"
        icon="exclamation-triangle-fill"
      />
      <span class="text-danger">{{ $t(`views.media.delete-media.warning`) }}</span>
      <b-table
        :borderless="true"
        :small="true"
        :items="desktops"
        :fields="fields"
      />
    </div>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          variant="danger"
          class="float-right"
          @click="deleteMedia"
        >
          {{ $t(`views.media.buttons.delete.title`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const desktops = computed(() => $store.getters.getMediaDesktops)

    const showDeleteMediaModal = computed({
      get: () => $store.getters.getShowDeleteMediaModal,
      set: (value) => $store.commit('showDeleteMediaModal', value)
    })

    const deleteMedia = () => {
      closeDeleteMediaModal()
      context.emit('deleteMedia')
    }

    const closeDeleteMediaModal = () => {
      $store.dispatch('showDeleteMediaModal', false)
    }

    return { desktops, showDeleteMediaModal, deleteMedia, closeDeleteMediaModal }
  },
  data () {
    return {
      fields: [
        {
          key: 'kind',
          sortable: true,
          label: i18n.t('views.media.delete-media.table-header.kind'),
          thStyle: { width: '20%' }
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.media.delete-media.table-header.name'),
          thStyle: { width: '20%' }
        },
        {
          key: 'userName',
          sortable: true,
          label: i18n.t('views.media.delete-media.table-header.user'),
          thStyle: { width: '20%' }
        }
      ]
    }
  }
}
</script>
