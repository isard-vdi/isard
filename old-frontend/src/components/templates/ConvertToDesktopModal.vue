<template>
  <b-modal
    id="ConvertToDesktopModal"
    v-model="showConvertToDesktopModal"
    size="xl"
    :title="headerTitle"
    centered
    :header-class="headerClass"
    @hidden="closeConvertToDesktopModal"
  >
    <div class="mx-4">
      <template v-if="canConvert">
        <span
          class="text-info"
        >
          <b-icon
            class="mr-2"
            variant="info"
            icon="info-circle-fill"
          />
          {{ $t(`views.templates.modal.convert.rename.title`, {name : $store.getters.getTemplateName}) }}
          <p class="text-info">
            {{ $t(`views.templates.modal.convert.warning.recyclebin`) }}
          </p>
        </span>

        <b-form
          inline
          class="flex-grow-1 mr-4 mt-2"
        >
          <label
            for="input-name"
            class="mr-sm-2"
          >
            {{ $t(`views.templates.modal.convert.rename.label`) }}
          </label>
          <b-form-input
            id="input-name"
            v-model="name"
            size="sm"
            class="flex-grow-1"
            :placeholder="$store.getters.getTemplateName"
            maxlength="50"
            :disabled="derivatives.pending"
          />
        </b-form>
      </template>

      <span
        v-if="hasWarnings"
        class="text-danger"
      >
        <p
          v-if="derivatives.is_duplicated"
        >
          <b-icon
            class="mr-2"
            variant="danger"
            icon="exclamation-triangle-fill"
          />
          {{ $t(`views.templates.modal.convert.warning.duplicate`) }}
        </p>
        <p v-else>
          <b-icon
            class="mr-2"
            variant="danger"
            icon="exclamation-triangle-fill"
          />
          <span v-if="hasDerivatives">
            {{ $t(`views.templates.modal.convert.warning.title`) }}
          </span>
          <span v-if="derivatives.pending">
            {{ $t(`views.templates.modal.convert.warning.pending`, {ammount: derivativesAmount }) }}
          </span>
        </p>
      </span>

      <IsardTable
        v-if="hasDerivatives && derivativesView === 'list'"
        class="mt-3"
        :items="derivativesFiltered.domains.concat(derivatives.deployments)"
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
      <!-- TODO: User this check when allowing automatically deleting the user dependencies -->
      <!-- <b-form-checkbox
        v-if="canConvert && derivativesFiltered.domains.length > 0"
        id="checkbox-confirmation"
        v-model="confirmation"
      >
        {{ $t(`views.templates.modal.convert.warning.confirm`) }}
        <b-form-invalid-feedback :state="confirmation">
          {{ $t(`views.templates.modal.convert.warning.confirm-unchecked`) }}
        </b-form-invalid-feedback>
      </b-form-checkbox> -->
    </div>
    <template #modal-footer>
      <div class="w-100 d-flex flex-row justify-content-between align-items-center">
        <p
          v-if="hasWarnings"
          class="text-danger my-2 mr-4"
        >
          {{ $t(`views.templates.modal.convert.warning.footer`) }}
        </p>
        <span class="flex-grow-1" />
        <b-button
          squared
          :variant="hasWarnings ? 'secondary' : 'purple'"
          :disabled="hasWarnings"
          @click="convertToDesktop"
        >
          {{ $t(`views.templates.modal.convert.button.apply`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>

<script>
import { computed, ref, watch } from '@vue/composition-api'
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

    // Remove the template itself from the derivatives list
    const derivativesFiltered = computed(() => ({
      domains: derivatives.value.domains
        .filter(domain => domain.id !== $store.getters.getTemplateId)
    }))

    const derivativesAmount = computed(() =>
      derivativesFiltered.value.domains.length +
      derivatives.value.deployments.length
    )

    const name = ref('')
    watch(() => $store.getters.getTemplateName, (newVal) => {
      name.value = newVal
    })

    const showConvertToDesktopModal = computed({
      get: () => $store.getters.getShowConvertToDesktopModal,
      set: (value) => $store.commit('setShowConvertToDesktopModal', value)
    })

    // const confirmation = ref(false)

    const convertToDesktop = () => {
      if (!hasWarnings.value) {
        $store.dispatch('convertToDesktop', { templateId: $store.getters.getTemplateId, name: name.value }).then(() => {
          closeConvertToDesktopModal()
        })
      }
    }
    const closeConvertToDesktopModal = () => {
      $store.commit('setShowConvertToDesktopModal', false)
      // confirmation.value = false
    }

    const headerTitle = computed(() => {
      if (derivativesFiltered.value.domains.length > 0 || derivatives.value.deployments.length > 0 || derivatives.value.pending) {
        return i18n.t('views.templates.modal.convert.title.warning')
      } else {
        return i18n.t('views.templates.modal.convert.title.ok', { name: $store.getters.getTemplateName })
      }
    })

    const headerClass = computed(() => {
      if (derivativesFiltered.value.domains.length > 0 || derivatives.value.deployments.length > 0 || derivatives.value.pending) {
        return 'bg-red text-white'
      } else {
        return 'bg-purple text-white'
      }
    })

    const hasDerivatives = computed(() => {
      // Domain can only be 1, that is the template itself
      return derivativesFiltered.value.domains.length > 0 || derivatives.value.deployments.length > 0 || derivatives.value.pending
    })
    const hasWarnings = computed(() => hasDerivatives.value || derivatives.value.is_duplicated)
    const canConvert = computed(() => !hasWarnings.value)

    const derivativesView = computed(() => $store.getters.getDerivativesView)

    return {
      perPage,
      pageOptions,
      filterOn,
      loading,
      name,
      closeConvertToDesktopModal,
      showConvertToDesktopModal,
      // confirmation,
      convertToDesktop,
      derivatives,
      derivativesFiltered,
      derivativesAmount,
      headerTitle,
      headerClass,
      derivativesView,
      hasDerivatives,
      hasWarnings,
      canConvert
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'kind',
          sortable: true,
          label: i18n.t('views.templates.modal.convert.table-header.kind'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.templates.modal.convert.table-header.name'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        },
        {
          key: 'user',
          sortable: true,
          label: i18n.t('views.templates.modal.convert.table-header.user'),
          thStyle: { width: '20%' },
          formatter: (value) => (value || '--')
        }
      ]
    }
  }
}
</script>

<style>
  .convert-row {
    margin: 0 !important;
    box-shadow: none !important;
    -webkit-box-shadow: none !important;
    border-spacing: 0px !important;
    height: 2rem !important;
  }

  .convert-row td {
    padding: 0 0.75rem !important;
    border: none !important;
  }

  .convert-table th {
    border: none !important;
  }

  .convert-table table {
    border-spacing: 0 !important;
    border-collapse: collapse !important;
  }
</style>
