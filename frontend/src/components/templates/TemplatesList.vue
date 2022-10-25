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
        <!-- Filter -->
        <b-row class="mt-4">
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
                :placeholder="$t('forms.filter-placeholder')"
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
                aria-controls="template-table"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-row>

        <b-row>
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-start"
          >
            <b-table
              id="template-table"
              :items="templates"
              :fields="shared ? sharedFields : fields"
              :responsive="true"
              :per-page="perPage"
              :current-page="currentPage"
              :filter="filter"
              :filter-included-fields="filterOn"
              @filtered="onFiltered"
            >
              <template #cell(image)="data">
                <!-- IMAGE -->
                <div
                  class="rounded-circle bg-red"
                  :style="{'background-image': `url('..${data.item.image.url}')`}"
                />
              </template>
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
                    class="rounded-circle px-2 mr-2 btn-blue"
                    :title="$t('views.templates.buttons.edit.title')"
                    @click="onClickGoToEditTemplate(data.item.id)"
                  >
                    <b-icon
                      icon="pencil-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    class="rounded-circle px-2 mr-2 btn-dark-blue"
                    :title="$t('views.templates.buttons.allowed.title')"
                    @click="showAllowedModal(data.item)"
                  >
                    <b-icon
                      icon="people-fill"
                      scale="0.75"
                    />
                  </b-button>
                  <b-button
                    class="rounded-circle px-2 mr-2"
                    :class="enabledClass(data.item)"
                    :title="data.item.enabled ? $t('views.templates.buttons.disable.title') : $t('views.templates.buttons.enable.title')"
                    @click="toggleEnabled(data.item)"
                  >
                    <b-icon
                      :icon="toggleEnabledIcon(data.item)"
                      scale="0.75"
                    />
                  </b-button>
                  <!-- Pagination -->
                </div>
              </template>
            </b-table>
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
                  aria-controls="template-table"
                  size="sm"
                />
              </b-col>
            </b-row>
          </b-col>
        </b-row>
      </b-skeleton-wrapper>
    </b-container>
  </div>
</template>
<script>
import i18n from '@/i18n'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import { ref, reactive, watch } from '@vue/composition-api'

export default {
  components: { ListItemSkeleton },
  props: {
    templates: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    },
    shared: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  setup (props, context) {
    const $store = context.root.$store

    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const currentPage = ref(1)
    const totalRows = ref(1)
    const filter = ref('')
    const filterOn = reactive(['name', 'description'])

    const showAllowedModal = (template) => {
      $store.dispatch('fetchAllowed', { table: 'domains', id: template.id })
    }

    const enabledClass = (template) => {
      return template.enabled ? 'btn-grey' : 'btn-blue'
    }

    const toggleEnabledIcon = (template) => {
      return template.enabled ? 'eye-slash-fill' : 'eye-fill'
    }

    const toggleEnabled = (template) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('toggleEnabled', { id: template.id, enabled: !template.enabled })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t(template.enabled ? 'messages.confirmation.disable-template' : 'messages.confirmation.enable-template', { name: template.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const onClickGoToEditTemplate = (templateId) => {
      $store.dispatch('goToEditDomain', templateId)
    }

    watch(() => props.templates, (newVal, prevVal) => {
      totalRows.value = newVal.length
    })

    return {
      showAllowedModal,
      enabledClass,
      toggleEnabledIcon,
      toggleEnabled,
      onFiltered,
      onClickGoToEditTemplate,
      filter,
      filterOn,
      perPage,
      pageOptions,
      currentPage,
      totalRows
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'image',
          sortable: false,
          label: '',
          thStyle: { width: '5%' },
          tdClass: 'image position-relative'
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.templates.table-header.name'),
          thStyle: { width: '25%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.templates.table-header.description'),
          thStyle: { width: '35%' }
        },
        {
          key: 'actions',
          label: i18n.t('views.templates.table-header.actions'),
          thStyle: { width: '5%' }
        }
      ],
      sharedFields: [
        {
          key: 'image',
          sortable: false,
          label: '',
          thStyle: { width: '5%' },
          tdClass: 'image position-relative'
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.templates.table-header.name'),
          thStyle: { width: '25%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.templates.table-header.description'),
          thStyle: { width: '35%' }
        }
      ]
    }
  }
}
</script>
