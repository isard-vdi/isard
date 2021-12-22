<template>
  <b-container fluid class="desktop-container pl-3 pr-3 pl-xl-5 pr-xl-5">
    <b-form @submit.prevent="submitForm" class="m-0">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2"><strong>{{ $t('forms.new-desktop.title') }}</strong></h4>
      </b-row>

      <!-- Name -->
      <b-row>
        <b-col cols="4" xl="2"><label for="desktopNameField">{{ $t('forms.new-desktop.name') }}</label></b-col>
        <b-col cols="6" xl="4">
          <b-form-input
            id="desktopNameField"
            type="text"
            v-model="desktopName"
            size="sm"
            @blur="v$.desktopName.$touch"/>
            <div class="isard-form-error" v-if="v$.desktopName.$error">{{ $t(`validations.${v$.desktopName.$errors[0].$validator}`, { property: $t('forms.new-desktop.name'), model: desktopName.length,  min: 4, max: 40 }) }}</div>
        </b-col>
      </b-row>

      <!-- Description -->
      <b-row class="mt-4">
        <b-col cols="4" xl="2"><label for="desktopDescriptionField">{{ $t('forms.new-desktop.description') }}</label></b-col>
        <b-col cols="6" xl="4">
          <b-form-input
            id="desktopDescriptionField"
            type="text"
            v-model="description"
            size="sm"/>
        </b-col>
      </b-row>

      <!-- Template section title -->
      <b-row class="mt-2 mt-xl-5">
        <h5 class="p-2 mt-2"><strong>{{ $t('forms.new-desktop.section-title-template') }}</strong></h5>
      </b-row>

      <!-- Table validation hidden field -->
      <b-row>
        <b-col cols="4">
          <b-form-input
            id="tableValidationField"
            type="text"
            v-model="selectedTemplateId"
            class="d-none"
            @change="v$.selectedTemplateId.$touch"/>
            <div class="isard-form-error" v-if="v$.selectedTemplateId.$error">{{ $t(`validations.${v$.selectedTemplateId.$errors[0].$validator}`, { property: `${$t("forms.new-desktop.desktop-template")}` }) }}</div>
        </b-col>
      </b-row>

      <!-- Filter -->
      <b-row class="mt-2">
          <b-col cols="2"><label for="filter-input">{{ $t('forms.new-desktop.filter') }}</label></b-col>
          <b-col cols="8" md="6" lg="4" xl="4">
            <b-input-group size="sm">
              <b-form-input
                id="filter-input"
                v-model="filter"
                type="search"
                :placeholder="$t('forms.new-desktop.filter-placeholder')"
              ></b-form-input>
              <b-input-group-append>
                <b-button :disabled="!filter" @click="filter = ''">{{ $t('forms.clear') }}</b-button>
              </b-input-group-append>
            </b-input-group>
          </b-col>
      </b-row>

      <!-- Table -->
      <b-row class="mt-4">
        <b-col>
          <b-table
          id="desktops-table"
          striped
          hover
          :items="items"
          :per-page="perPage"
          :current-page="currentPage"
          :filter="filter"
          :filter-included-fields="filterOn"
          :fields="fields"
          small
          @filtered="onFiltered"
          select-mode="single"
          selected-variant="primary"
          selectable
          @row-selected="onRowSelected">
            <!-- Scoped slot for line selected column -->
          <template #cell(selected)="{ rowSelected }">
            <template v-if="rowSelected">
              <span aria-hidden="true">&check;</span>
            </template>
            <template v-else>
              <span aria-hidden="true">&nbsp;</span>
            </template>
          </template>
        </b-table>
        </b-col>
      </b-row>
      <!-- Pagination -->
      <b-row>
        <b-col>
          <b-pagination
          v-model="currentPage"
          :total-rows="totalRows"
          :per-page="perPage"
          aria-controls="desktops-table"
          size="sm">
          </b-pagination>
        </b-col>
      </b-row>

      <!-- Buttons -->
      <b-row align-h="end">
        <b-button size="md" class="btn-red rounded-pill mt-4 mr-2" @click="navigate('desktops')">{{ $t('forms.cancel') }}</b-button>
        <b-button type="submit" size="md" class="btn-green rounded-pill mt-4 ml-2 mr-5">{{ $t('forms.create') }}</b-button>
      </b-row>
  </b-form>
  </b-container>
</template>

<script>
import i18n from '@/i18n'
import { reactive, ref, computed } from '@vue/composition-api'
import { mapActions } from 'vuex'
import useVuelidate from '@vuelidate/core'
import { required, maxLength, minLength } from '@vuelidate/validators'

// const inputFormat = helpers.regex('inputFormat', /^1(3|4|5|7|8)\d{9}$/) // /^\D*7(\D*\d){12}\D*$'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  setup (props, context) {
    const $store = context.root.$store
    $store.dispatch('fetchTemplates')

    const desktopName = ref('')
    const description = ref('')
    const perPage = ref(5)
    const currentPage = ref(1)
    const filter = ref('')
    const filterOn = reactive([])
    const selected = ref([])
    const selectedTemplateId = computed(() => selected.value[0] ? selected.value[0].id : '')

    const items = computed(() => $store.getters.getTemplates)

    const fields = reactive([
      {
        key: 'selected',
        label: i18n.t('forms.new-desktop.template-table-column-headers.selected'),
        thClass: 'col-1 d-none d-md-inline-block',
        tdClass: 'col-1 d-none d-md-inline-block'
      },
      {
        key: 'name',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.name'),
        thClass: 'col-3'
      },
      {
        key: 'description',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.description'),
        thClass: 'col-4 d-none d-xl-inline-block',
        tdClass: 'col-4 d-none d-xl-inline-block'
      },
      {
        key: 'category',
        label: i18n.t('forms.new-desktop.template-table-column-headers.category'),
        sortable: true,
        thClass: 'col-4 d-none d-md-inline-block',
        tdClass: 'col-4 d-none d-md-inline-block'
      },
      {
        key: 'group',
        label: i18n.t('forms.new-desktop.template-table-column-headers.group'),
        sortable: false,
        thClass: 'col-2 d-none d-md-inline-block',
        tdClass: 'col-2 d-none d-md-inline-block'
      },
      {
        key: 'userName',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.user'),
        thClass: 'col-2 d-none d-md-inline-block',
        tdClass: 'col-2 d-none d-md-inline-block'
      }
    ])

    return {
      desktopName,
      description,
      items,
      fields,
      perPage,
      currentPage,
      filter,
      filterOn,
      selected,
      selectedTemplateId,
      v$: useVuelidate()
    }
  },
  validations () {
    return {
      desktopName: {
        required,
        maxLengthValue: maxLength(40),
        minLengthValue: minLength(4),
        inputFormat
      },
      selectedTemplateId: { required }
    }
  },
  data () {
    return {
      totalRows: 1
    }
  },
  mounted () {
    this.totalRows = this.items.length
  },
  methods: {
    ...mapActions([
      'createNewDesktop',
      'navigate'
    ]),
    onFiltered (filteredItems) {
      // Trigger pagination to update the number of buttons/pages due to filtering
      this.totalRows = filteredItems.length
      this.currentPage = 1
    },
    onRowSelected (items) {
      this.selected = items
    },
    async submitForm () {
      const isFormCorrect = await this.v$.$validate()

      if (isFormCorrect) {
        this.createNewDesktop({ id: this.selected[0].id, name: this.desktopName, description: this.description })
      }
    }
  }
}
</script>
