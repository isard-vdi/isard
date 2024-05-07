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
      <DomainInfo />

      <!-- Table validation hidden field -->
      <b-row>
        <h4 class="p-1 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.new-desktop.section-title-template') }}</strong>
        </h4>
        <b-col cols="4">
          <b-form-input
            v-model="selectedTemplateId"
            type="text"
            class="d-none"
            @change="v$.selectedTemplateId.$touch"
          />
          <div
            v-if="v$.selectedTemplateId.$error"
            id="selectedTemplateIdError"
            class="text-danger"
          >
            {{ $t(`validations.${v$.selectedTemplateId.$errors[0].$validator}`, { property: `${$t("forms.new-desktop.desktop-template")}` }) }}
          </div>
        </b-col>
      </b-row>

      <!-- Table -->
      <b-skeleton-wrapper
        :loading="!getTemplatesLoaded"
        class="card-body mt-2 d-flex flex-row flex-wrap justify-content-center"
      >
        <template #loading>
          <DesktopNewSkeleton />
        </template>
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
          <b-row
            class="ml-auto mr-2"
          >
            <b-col>
              <b-form-group
                :label="$t('forms.show-pages')"
                label-for="per-page-select"
                label-cols-md="5"
                label-align-sm="right"
                class="text-medium-gray mr-2 mr-lg-0"
              >
                <b-form-select
                  id="per-page-select"
                  v-model="perPage"
                  class="card-list"
                  :label="$t('forms.show-pages')"
                  :options="pageOptions"
                  size="sm"
                />
              </b-form-group>
            </b-col>
            <b-col>
              <b-pagination
                v-model="currentPage"
                :total-rows="totalRows"
                :per-page="perPage"
                aria-controls="selectedTemplateId"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>
        <b-table
          id="selectedTemplateId"
          ref="templateTable"
          striped
          hover
          :items="items"
          :per-page="perPage"
          :current-page="currentPage"
          :filter="filter"
          :filter-included-fields="filterOn"
          :fields="fields"
          :responsive="true"
          :head-row-variant="v$.selectedTemplateId.$error ? 'danger' : ''"
          :sort-by.sync="sortBy"
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
            <div class="position-relative">
              <b-icon
                v-if="data.item.status.toLowerCase() === desktopStates.failed"
                v-b-tooltip="{ title: $t(`errors.template_failed`), placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
                icon="exclamation-triangle-fill"
                variant="danger"
                class="danger-icon position-absolute cursor-pointer"
              />
              <img
                :src="`..${data.item.image.url}`"
                alt=""
                style="height: 2rem; border: 1px solid #555;"
              >
            </div>
          </template>
        </b-table>
        <b-row class="mt-4">
          <b-row
            class="ml-auto mr-2"
          >
            <b-col>
              <b-form-group
                :label="$t('forms.show-pages')"
                label-for="per-page-select"
                label-cols-md="5"
                label-align-sm="right"
                class="text-medium-gray mr-2 mr-lg-0"
              >
                <b-form-select
                  id="per-page-select"
                  v-model="perPage"
                  class="card-list"
                  :label="$t('forms.show-pages')"
                  :options="pageOptions"
                  size="sm"
                />
              </b-form-group>
            </b-col>
            <b-col>
              <b-pagination
                v-model="currentPage"
                :total-rows="totalRows"
                :per-page="perPage"
                aria-controls="selectedTemplateId"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>
      </b-skeleton-wrapper>

      <!-- Advanced options section title -->
      <b-row>
        <h4
          class="p-2 cursor-pointer"
          @click="collapseVisible = !collapseVisible"
        >
          <strong>{{ $t('forms.new-desktop.section-title-advanced') }}</strong>
          <b-icon
            class="ml-2"
            :icon="collapseVisible ? 'chevron-up' : 'chevron-down'"
          />
        </h4>
      </b-row>

      <div>
        <b-collapse
          id="collapse-advanced"
          v-model="collapseVisible"
        >
          <DomainViewers />
          <DomainHardware />
          <DomainBookables />
          <DomainMedia />
          <DomainImage />
        </b-collapse>
      </div>

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
import DesktopNewSkeleton from '@/components/desktops/DesktopNewSkeleton.vue'
import { reactive, ref, computed, watch, onUnmounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
import DomainViewers from '@/components/domain/DomainViewers.vue'
import DomainHardware from '@/components/domain/DomainHardware.vue'
import DomainMedia from '@/components/domain/DomainMedia.vue'
import DomainBookables from '@/components/domain/DomainBookables.vue'
import DomainImage from '@/components/domain/DomainImage.vue'
import DomainInfo from '@/components/domain/DomainInfo.vue'
import { ErrorUtils } from '@/utils/errorUtils'
import { desktopStates } from '@/shared/constants'

const templateTable = ref(null)

export default {
  components: {
    DesktopNewSkeleton,
    DomainViewers,
    DomainHardware,
    DomainMedia,
    DomainBookables,
    DomainImage,
    DomainInfo
  },
  setup (props, context) {
    const collapseVisible = ref(false)
    const $store = context.root.$store
    $store.dispatch('fetchAllowedTemplates', 'all')
    $store.dispatch('fetchDesktopImages')

    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }

    const domain = computed(() => $store.getters.getDomain)
    // Templates table
    const perPage = ref(20)
    const currentPage = ref(1)
    const pageOptions = ref([5, 10, 20, 30, 50, 100])
    const filter = ref('')
    const filterOn = reactive(['name', 'description', 'categoryName', 'groupName', 'userName'])
    const selected = ref([])
    const selectedTemplateId = computed(() => selected.value[0] ? selected.value[0].id : '')
    const totalRows = ref(1)
    const getTemplatesLoaded = computed(() => $store.getters.getTemplatesLoaded)
    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }
    const sortBy = 'name'

    const onRowSelected = (item) => {
      if (item[0] && item[0].status.toLowerCase() === desktopStates.failed) {
        ErrorUtils.showErrorNotification(context.root.$snotify, i18n.t('errors.template_failed'), 'centerTop', 5000)
        templateTable.value.clearSelected()
      } else {
        selected.value = item
      }
    }

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

    // Set the advanced data when selecting a template
    watch(selectedTemplateId, (newVal, prevVal) => {
      if (newVal) {
        $store.dispatch('fetchDomain', newVal)
      }
    })

    // Selected template validation
    const v$ = useVuelidate({
      selectedTemplateId: { required }
    }, { selectedTemplateId })

    // Send data to api
    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      // Parse viewers data
      const viewers = {}
      for (let i = 0; i < domain.value.guestProperties.viewers.length; i++) {
        Object.assign(viewers, domain.value.guestProperties.viewers[i])
      }
      // Parse isos data
      const isos = domain.value.hardware.isos.map((value) => {
        return { id: value.id }
      })
      // Create the data object that will be send
      const domainData = {
        template_id: selected.value[0].id,
        name: domain.value.name,
        description: domain.value.description,
        guest_properties: {
          credentials: {
            username: domain.value.guestProperties.credentials.username,
            password: domain.value.guestProperties.credentials.password
          },
          fullscreen: domain.value.guestProperties.fullscreen,
          viewers: viewers
        },
        hardware: {
          boot_order: domain.value.hardware.bootOrder,
          disk_bus: domain.value.hardware.diskBus,
          disks: domain.value.hardware.disks,
          floppies: domain.value.hardware.floppies,
          interfaces: domain.value.hardware.interfaces,
          isos: isos,
          memory: domain.value.hardware.memory,
          vcpus: domain.value.hardware.vcpus,
          videos: domain.value.hardware.videos,
          reservables: domain.value.reservables
        },
        image: domain.value.image
      }
      $store.dispatch('createNewDesktop', domainData)
    }

    onUnmounted(() => {
      $store.dispatch('resetDomainState')
      $store.dispatch('resetTemplatesState')
    })

    return {
      collapseVisible,
      items,
      fields,
      perPage,
      currentPage,
      pageOptions,
      filter,
      filterOn,
      selected,
      selectedTemplateId,
      totalRows,
      getTemplatesLoaded,
      domain,
      submitForm,
      navigate,
      onRowSelected,
      onFiltered,
      v$,
      templateTable,
      desktopStates,
      sortBy
    }
  }
}
</script>
