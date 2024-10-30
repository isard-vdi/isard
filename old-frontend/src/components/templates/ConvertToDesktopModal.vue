<template>
  <b-modal
    id="ConvertToDesktopModal"
    v-model="ShowConvertToDesktopModal"
    size="xl"
    :title="headerTitle"
    centered
    :header-class="headerClass"
    @hidden="closeConvertToDesktopModal"
  >
    <div class="mx-4">
      <template v-if="!derivatives.pending">
        <span
          class="text-info"
        >
          <b-icon
            class="mr-2"
            variant="info"
            icon="info-circle-fill"
          />
          {{ $t(`views.templates.modal.convert.rename.title`, {name : $store.getters.getTemplateName}) }}
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

      <hr
        v-if="(!derivatives.pending) && (derivativesFiltered.domains.length > 0 || derivatives.pending || derivatives.is_duplicated )"
      >

      <span
        v-if="derivativesFiltered.domains.length > 0 || derivatives.pending || derivatives.is_duplicated"
        class="text-danger"
      >
        <p
          v-if="derivativesFiltered.domains.length > 0"
        >
          <b-icon
            class="mr-2"
            variant="danger"
            icon="exclamation-triangle-fill"
          />
          {{ $t(`views.templates.modal.convert.warning.title`) }}
        </p>
        <p
          v-if="derivatives.pending"
        >
          {{ $t(`views.templates.modal.convert.warning.pending`, {ammount: derivativesAmount }) }}
        </p>
        <p
          v-if="derivatives.is_duplicated"
        >
          {{ $t(`views.templates.modal.convert.warning.duplicate`) }}
        </p>
        <!-- <p
          v-else
        >
          {{ $t(`views.templates.modal.convert.warning.delete`) }}
        </p> -->
      </span>

      <!-- <ul
        v-if="derivativesFiltered.domains.length > 0"
        class="nav nav-tabs"
      >
        <li class="nav-item">
          <span
            class="nav-link cursor-pointer"
            :class="{ 'active': derivativesView === 'list' }"
            @click="$store.commit('setDerivativesView', 'list')"
          >
            <b-icon
              icon="list-ul"
            />
            list
          </span>
        </li>
        <li class="nav-item">
          <span
            class="nav-link cursor-pointer"
            :class="{ 'active': derivativesView === 'diagram' }"
            @click="$store.commit('setDerivativesView', 'diagram')"
          >
            <b-icon
              icon="diagram2-fill"
            />
            diagram
          </span>
        </li>
      </ul> -->

      <IsardTable
        v-if="derivativesFiltered.domains.length > 0 && derivativesView === 'list'"
        class="mt-3"
        :items="derivativesFiltered.domains"
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

      <b-form-checkbox
        v-if="!derivativesFiltered.domains.length && (!derivatives.pending && derivativesFiltered.domains.length > 0)"
        id="checkbox-confirmation"
        v-model="confirmation"
        :state="checkState"
      >
        {{ $t(`views.templates.modal.convert.warning.confirm`) }}
        <b-form-invalid-feedback :state="checkState">
          {{ $t(`views.templates.modal.convert.warning.confirm-unchecked`) }}
        </b-form-invalid-feedback>
      </b-form-checkbox>
    </div>
    <template #modal-footer>
      <div class="w-100 d-flex flex-row justify-content-between align-items-center">
        <p
          v-if="derivativesFiltered.domains.length > 0|| derivatives.pending"
          class="text-danger my-2 mr-4"
        >
          {{ $t(`views.templates.modal.convert.warning.footer`) }}
        </p>
        <span class="flex-grow-1" />
        <b-button
          squared
          :variant="derivativesFiltered.domains.length > 0 || derivatives.pending || derivatives.is_duplicated ? 'secondary' : 'purple'"
          :disabled="derivativesFiltered.domains.length > 0 || derivatives.pending || derivatives.is_duplicated"
          @click="ConvertToDesktop"
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

    const derivativesFiltered = ref({ domains: [] })
    watch(() => $store.getters.getTemplateDerivatives.domains, (newVal) => {
      derivativesFiltered.value.domains = newVal.filter(domain => Object.keys(domain).length !== 0).filter(domain => domain.id !== $store.getters.getTemplateId)
    })

    const derivativesAmount = ref(0)
    watch(() => $store.getters.getTemplateDerivatives.domains, (newVal) => {
      derivativesAmount.value = newVal.filter(domain => Object.keys(domain).length === 0).length
    })

    const name = ref('')
    watch(() => $store.getters.getTemplateName, (newVal) => {
      name.value = newVal
    })

    const ShowConvertToDesktopModal = computed(() => $store.getters.getShowConvertToDesktopModal)

    const checkState = ref(null)
    const confirmation = ref(false)
    watch(() => confirmation.value, (newVal, oldVal) => {
      if (newVal === false && oldVal === true) {
        checkState.value = false
      }
      if (newVal === true) {
        checkState.value = true
      }
    })

    const ConvertToDesktop = () => {
      if (confirmation.value === true || !(derivativesFiltered.value.domains.length > 0 || derivatives.value.pending)) {
        $store.dispatch('ConvertToDesktop', { templateId: $store.getters.getTemplateId, name: name.value }).then(() => {
          closeConvertToDesktopModal()
        })
      } else {
        checkState.value = false
      }
    }
    const closeConvertToDesktopModal = () => {
      $store.commit('setShowConvertToDesktopModal', false)
      confirmation.value = false
      checkState.value = null
    }

    const headerTitle = computed(() => {
      if (derivativesAmount.value > 0) {
        return i18n.t('views.templates.modal.convert.title.warning')
      } else {
        return i18n.t('views.templates.modal.convert.title.ok', { name: $store.getters.getTemplateName })
      }
    })

    const headerClass = computed(() => {
      if (derivativesAmount.value > 0) {
        return 'bg-red text-white'
      } else {
        return 'bg-purple text-white'
      }
    })

    const sameName = computed(() => {
      if (name.value === $store.getters.getTemplateName) {
        return true
      } else {
        return false
      }
    })

    const derivativesView = computed(() => $store.getters.getDerivativesView)

    return {
      perPage,
      pageOptions,
      filterOn,
      loading,
      name,
      closeConvertToDesktopModal,
      ShowConvertToDesktopModal,
      confirmation,
      ConvertToDesktop,
      derivatives,
      derivativesFiltered,
      derivativesAmount,
      headerTitle,
      headerClass,
      sameName,
      derivativesView,
      checkState
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
