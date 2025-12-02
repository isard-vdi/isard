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
      <span v-else-if="derivatives.deployments.length > 0">
        <b-icon
          class="mr-2"
          variant="warning"
          icon="exclamation-triangle-fill"
        />
        {{ $t(`views.templates.modal.delete.warning.deployments`) }}
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
      <IsardTable
        class="mt-3"
        :items="derivatives.domains.concat(derivatives.deployments)"
        :fields="fields"
        :sort-by="fields.name"
        :sort-desc="true"
        :default-per-page="perPage"
        :page-options="pageOptions"
        :filter-on="filterOn"
        :loading="loading"
        row-class="convert-row"
        table-class="convert-table"
        :hide-components="['bottomPagination']"
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
import { computed, ref } from '@vue/composition-api'
import IsardTable from '@/components/shared/IsardTable.vue'
import i18n from '@/i18n'

export default {
  components: {
    IsardTable
  },
  setup (_, context) {
    const $store = context.root.$store
    const perPage = ref(10)
    const pageOptions = ref([6, 10, 20, 30, 50, 100])
    const filterOn = ref(['kind', 'name', 'user'])
    const loading = ref(false)

    const derivatives = computed(() => $store.getters.getTemplateDerivatives)
    const showDeleteTemplateModal = computed({
      get: () => $store.getters.getShowDeleteTemplateModal,
      set: (value) => $store.dispatch('showDeleteTemplateModal', value)
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
      derivatives,
      perPage,
      pageOptions,
      filterOn,
      loading
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
