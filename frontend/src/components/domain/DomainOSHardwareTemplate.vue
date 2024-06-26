<template>
  <div>
    <h4 class="my-2">
      <strong>{{ $t('forms.new-desktop.section-title-os-template') }}</strong>
    </h4>

    <!-- Table validation hidden field -->
    <b-row>
      <b-col cols="4">
        <b-form-input
          v-model="selectedOSTemplateId"
          type="text"
          class="d-none"
          @change="v$.selectedOSTemplateId.$touch"
        />
        <div
          v-if="v$.selectedOSTemplateId.$error"
          id="selectedOSTemplateIdError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.selectedOSTemplateId.$errors[0].$validator}`, { property: `${$t("forms.new-desktop.desktop-template")}` }) }}
        </div>
      </b-col>
    </b-row>

    <!-- Filter -->
    <b-row class="mt-2">
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
    <b-skeleton-wrapper
      :loading="!mediaInstallsLoaded"
      class="card-body pt-4 d-flex flex-row flex-wrap justify-content-center"
    >
      <template #loading>
        <DesktopNewSkeleton />
      </template>
      <b-row class="mt-4">
        <b-col>
          <b-table
            id="selectedOSTemplateId"
            striped
            hover
            :items="items"
            :per-page="perPage"
            :current-page="currentPage"
            :filter="filter"
            :filter-included-fields="filterOn"
            :fields="fields"
            :responsive="true"
            :head-row-variant="v$.selectedOSTemplateId.$error ? 'danger' : ''"
            small
            select-mode="single"
            selected-variant="primary"
            selectable
            tabindex="0"
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
    </b-skeleton-wrapper>

    <!-- Pagination -->
    <b-row>
      <b-col>
        <b-pagination
          v-model="currentPage"
          :total-rows="totalRows"
          :per-page="perPage"
          aria-controls="selectedOSTemplateId"
          size="sm"
        />
      </b-col>
    </b-row>
  </div>
</template>
<script>
import i18n from '@/i18n'
import DesktopNewSkeleton from '@/components/desktops/DesktopNewSkeleton.vue'
import { reactive, ref, computed, watch, onUnmounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'

export default {
  components: {
    DesktopNewSkeleton
  },
  setup (props, context) {
    const $store = context.root.$store
    $store.dispatch('fetchMediaInstalls')

    // Templates table
    const perPage = ref(5)
    const currentPage = ref(1)
    const filter = ref('')
    const filterOn = reactive([])
    const selectedOSTemplateId = computed(() => $store.getters.getSelectedOSTemplateId)
    const totalRows = ref(1)
    const mediaInstallsLoaded = computed(() => $store.getters.getMediaInstallsLoaded)
    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const onRowSelected = (items) => {
      $store.dispatch('setSelectedOSTemplateId', items[0].id)
    }

    const items = computed(() => $store.getters.getMediaInstalls)

    const fields = reactive([
      {
        key: 'name',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.name'),
        thClass: 'col-3'
      },
      {
        key: 'version',
        sortable: true,
        label: i18n.t('forms.new-desktop.template-table-column-headers.user'),
        thClass: 'col-2',
        tdClass: 'col-2'
      }
    ])

    watch(items, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })

    // Selected template validation
    const v$ = useVuelidate({
      selectedOSTemplateId: { required }
    }, { selectedOSTemplateId })

    onUnmounted(() => {
      $store.dispatch('resetDomainState')
      $store.dispatch('resetTemplatesState')
    })

    return {
      items,
      fields,
      perPage,
      currentPage,
      filter,
      filterOn,
      selectedOSTemplateId,
      totalRows,
      mediaInstallsLoaded,
      onRowSelected,
      onFiltered,
      v$
    }
  }
}
</script>
