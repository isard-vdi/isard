<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5 new-templates-list"
  >
    <b-form @submit.prevent="submitForm">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.new-desktop.title') }}</strong>
        </h4>
      </b-row>

      <!-- Name -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="desktopNameField">{{ $t('forms.new-desktop.name') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
        >
          <b-form-input
            id="desktopNameField"
            v-model="desktopName"
            type="text"
            size="sm"
            @blur="v$.desktopName.$touch"
          />
          <div
            v-if="v$.desktopName.$error"
            class="isard-form-error"
          >
            {{ $t(`validations.${v$.desktopName.$errors[0].$validator}`, { property: $t('forms.new-desktop.name'), model: desktopName.length, min: 4, max: 40 }) }}
          </div>
        </b-col>
      </b-row>

      <!-- Description -->
      <b-row class="mt-4">
        <b-col
          cols="4"
          xl="2"
        >
          <label for="desktopDescriptionField">{{ $t('forms.new-desktop.description') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
        >
          <b-form-input
            id="desktopDescriptionField"
            v-model="description"
            type="text"
            size="sm"
          />
        </b-col>
      </b-row>

      <!-- Template section title -->
      <b-row class="mt-2 mt-xl-5">
        <h5 class="p-2 mt-2">
          <strong>{{ $t('forms.new-desktop.section-title-template') }}</strong>
        </h5>
      </b-row>

      <!-- Table validation hidden field -->
      <b-row>
        <b-col cols="4">
          <b-form-input
            id="tableValidationField"
            v-model="selectedTemplateId"
            type="text"
            class="d-none"
            @change="v$.selectedTemplateId.$touch"
          />
          <div
            v-if="v$.selectedTemplateId.$error"
            class="isard-form-error"
          >
            {{ $t(`validations.${v$.selectedTemplateId.$errors[0].$validator}`, { property: `${$t("forms.new-desktop.desktop-template")}` }) }}
          </div>
        </b-col>
      </b-row>

      <!-- Filter -->
      <b-row class="mt-2">
        <b-col cols="2">
          <label for="filter-input">{{ $t('forms.new-desktop.filter') }}</label>
        </b-col>
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
              :placeholder="$t('forms.new-desktop.filter-placeholder')"
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
            :responsive="true"
            small
            select-mode="single"
            selected-variant="primary"
            selectable
            @filtered="onFiltered"
            @row-selected="onRowSelected"
          >
            <!-- Scoped slot for line selected column -->
            <template #cell(selected)="{ rowSelected }">
              <template v-if="rowSelected">
                <span aria-hidden="true">&check;</span>
              </template>
              <template v-else>
                <span aria-hidden="true">&nbsp;</span>
              </template>
            </template>

            <!-- Scoped slot for image -->
            <template #cell(image)="data">
              <img
                :src="`..${data.item.image.url}`"
                alt=""
                style="height: 2rem; border: 1px solid #555;"
              >
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
            size="sm"
          />
        </b-col>
      </b-row>

      <!-- Buttons -->
      <b-row align-h="end">
        <b-button
          size="md"
          class="btn-red rounded-pill mt-4 mr-2"
          @click="navigate('desktops')"
        >
          {{ $t('forms.cancel') }}
        </b-button>
        <b-button
          type="submit"
          size="md"
          class="btn-green rounded-pill mt-4 ml-2 mr-5"
        >
          {{ $t('forms.create') }}
        </b-button>
      </b-row>
    </b-form>
  </b-container>
</template>

<script>
import i18n from '@/i18n'
import { reactive, ref, computed, watch } from '@vue/composition-api'
import { mapActions } from 'vuex'
import useVuelidate from '@vuelidate/core'
import { required, maxLength, minLength } from '@vuelidate/validators'

// const inputFormat = helpers.regex('inputFormat', /^1(3|4|5|7|8)\d{9}$/) // /^\D*7(\D*\d){12}\D*$'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  setup (props, context) {
    const $store = context.root.$store
    $store.dispatch('fetchAllowedTemplates')

    const desktopName = ref('')
    const description = ref('')
    const perPage = ref(5)
    const currentPage = ref(1)
    const filter = ref('')
    const filterOn = reactive([])
    const selected = ref([])
    const selectedTemplateId = computed(() => selected.value[0] ? selected.value[0].id : '')
    const totalRows = ref(1)

    const items = computed(() => $store.getters.getTemplates)

    const fields = reactive([
      {
        key: 'selected',
        label: i18n.t('forms.new-desktop.template-table-column-headers.selected'),
        thClass: 'col-1',
        tdClass: 'col-1'
      },
      {
        key: 'image',
        sortable: false,
        label: i18n.t('forms.new-desktop.template-table-column-headers.image'),
        thClass: 'col-1'
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
        thClass: 'col-3',
        tdClass: 'col-3'
      },
      {
        key: 'categoryName',
        label: i18n.t('forms.new-desktop.template-table-column-headers.category'),
        sortable: true,
        thClass: 'col-2',
        tdClass: 'col-2'
      },
      {
        key: 'groupName',
        label: i18n.t('forms.new-desktop.template-table-column-headers.group'),
        sortable: false,
        thClass: 'col-2',
        tdClass: 'col-2'
      },
      {
        key: 'userName',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.user'),
        thClass: 'col-2',
        tdClass: 'col-2'
      }
    ])

    watch(items, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })

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
      v$: useVuelidate(),
      totalRows
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
  destroyed () {
    this.$store.dispatch('resetTemplatesState')
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
        this.createNewDesktop({ template_id: this.selected[0].id, name: this.desktopName, description: this.description })
      }
    }
  }
}
</script>
