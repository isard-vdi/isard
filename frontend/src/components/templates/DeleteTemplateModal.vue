<template>
  <b-modal
    id="deleteTemplateModal"
    v-model="showDeleteTemplateModal"
    size="xl"
    :title="$t(`views.templates.modal.delete.title`)"
    centered
    header-class="
    bg-red
    text-white"
    @hidden="closeDeleteTemplateModal"
  >
    <div class="mx-4">
      <span
        v-if="derivatives.pending"
        class="text-danger"
      >
        <b-icon
          class="mr-2"
          variant="danger"
          icon="exclamation-triangle-fill"
        />
        {{ $t(`views.templates.modal.delete.warning.pending`) }}
      </span>
      <span
        v-else
        class="text-danger"
      >
        <b-icon
          class="mr-2"
          variant="danger"
          icon="exclamation-triangle-fill"
        />
        {{ $t(`views.templates.modal.delete.warning.delete`) }}
      </span>
      <b-table
        class="mt-3"
        :borderless="true"
        :small="true"
        :items="derivatives.domains"
        :fields="fields"
        :sort-by="fields.name"
        :sort-desc="true"
      />
    </div>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          :variant="derivatives.pending ? 'secondary' : 'danger'"
          class="float-right"
          :disabled="derivatives.pending"
          @click="deleteTemplate"
        >
          {{ $t(`views.templates.modal.delete.button.delete`) }}
        </b-button>
        <p
          v-if="derivatives.pending"
          class="text-danger my
          -2 ml-4"
        >
          {{ $t(`views.templates.modal.delete.warning.footer`) }}
        </p>
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

    const derivatives = computed(() => $store.getters.getTemplateDerivatives)

    const showDeleteTemplateModal = computed({
      get: () => $store.getters.getShowDeleteTemplateModal
    })

    const deleteTemplate = () => {
      $store.dispatch('deleteTemplate', { pending: $store.getters.getTemplateDerivatives.pending }).then(() => {
        closeDeleteTemplateModal()
      })
    }
    const closeDeleteTemplateModal = () => {
      $store.dispatch('showDeleteTemplateModal', false)
    }

    return {
      closeDeleteTemplateModal,
      showDeleteTemplateModal,
      deleteTemplate,
      derivatives
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'kind',
          sortable: true,
          label: i18n.t('views.templates.modal.delete.table-header.kind'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.templates.modal.delete.table-header.name'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        },
        {
          key: 'user',
          sortable: true,
          label: i18n.t('views.templates.modal.delete.table-header.user'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        }
      ]
    }
  }
}
</script>
