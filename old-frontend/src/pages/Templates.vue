<template>
  <b-container
    id="content"
    fluid
  >
    <b-tabs>
      <b-tab
        :active="currentTab === 'templates'"
        @click="updateCurrentTab('templates')"
      >
        <template #title>
          <b-spinner
            v-if="!(getTemplatesLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.templates.tabs.templates-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.templates.tabs.templates') }}</span>
        </template>
        <template v-if="getTemplatesLoaded && getTemplates.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.templates.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.templates.no-templates.subtitle') }}</p>
          </div>
        </template>
        <IsardTable
          v-else
          :items="getTemplates"
          :loading="!(getTemplatesLoaded)"
          :page-options="pageOptions"
          :default-per-page="perPage"
          :filter-on="filterOn"
          :row-class="rowClass"
          :fields="fields.filter(field => field.visible !== false)"
          class="px-5 pt-3"
        >
          <template #cell(image)="data">
            <b-icon
              v-if="data.item.status.toLowerCase() === desktopStates.failed"
              v-b-tooltip="{ title: $t(`errors.template_failed`), placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
              icon="exclamation-triangle-fill"
              variant="danger"
              class="danger-icon position-absolute cursor-pointer"
            />
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
          <template #cell(desktopSize)="data">
            <p class="text-dark-gray m-0">
              {{ (data.item.desktopSize / 1024 / 1024 / 1024).toFixed(1) + "GB" }}
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
              <!-- TODO: DESKTOP STORAGE PATH MUST NEVER BE IN TEMPLATE PATH -->
              <!-- <b-button
                class="rounded-circle px-2 mr-2 btn-purple"
                :title="$t('views.templates.buttons.convert.title')"
                @click="showConvertToDesktopModal(data.item)"
              >
                <b-icon
                  icon="tv"
                  scale="0.75"
                />
              </b-button> -->
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
              <b-button
                class="rounded-circle px-2 mr-2 btn-red"
                :title="$t('views.templates.buttons.delete.title')"
                @click="showDeleteModal(data.item.id)"
              >
                <b-icon
                  icon="trash-fill"
                  scale="0.75"
                />
              </b-button>
            </div>
          </template>
        </IsardTable>
      </b-tab>
      <b-tab
        :active="currentTab === 'sharedTemplates'"
        @click="updateCurrentTab('sharedTemplates')"
      >
        <template #title>
          <b-spinner
            v-if="!(getSharedTemplatesLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.templates.tabs.shared-templates-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.templates.tabs.shared-templates') }}</span>
        </template>
        <template v-if="getSharedTemplatesLoaded && getSharedTemplates.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.templates.no-shared-templates.title') }}</strong></h3>
            <p>{{ $t('views.templates.no-shared-templates.subtitle') }}</p>
          </div>
        </template>
        <IsardTable
          v-else
          :items="getSharedTemplates"
          :loading="!(getSharedTemplatesLoaded)"
          :page-options="pageOptions"
          :default-per-page="perPage"
          :filter-on="filterOn"
          :row-class="rowClass"
          :fields="sharedFields.filter(field => field.visible !== false)"
          class="px-5 pt-3"
        >
          <template #cell(image)="data">
            <b-icon
              v-if="data.item.status.toLowerCase() === desktopStates.failed"
              v-b-tooltip="{ title: $t(`errors.template_failed`), placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
              icon="exclamation-triangle-fill"
              variant="danger"
              class="danger-icon position-absolute cursor-pointer"
            />
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
          <template #cell(desktopSize)="data">
            <p class="text-dark-gray m-0">
              {{ (data.item.desktopSize / 1024 / 1024 / 1024).toFixed(1) + "GB" }}
            </p>
          </template>
          <template #cell(actions)="data">
            <div class="d-flex justify-content-center align-items-center">
              <b-button
                class="rounded-circle px-2 mr-2 btn-green"
                :title="$t('views.templates.buttons.duplicate.title')"
                @click="onClickGoToDuplicate(data.item.id)"
              >
                <b-icon
                  icon="files"
                  scale="0.75"
                />
              </b-button>
            </div>
          </template>
        </IsardTable>
      </b-tab>
    </b-tabs>
    <AllowedModal @updateAllowed="updateAllowed" />
    <ConvertToDesktopModal />
    <DeleteTemplateModal />
  </b-container>
</template>
<script>
// @ is an alias to /src
import IsardTable from '../components/shared/IsardTable.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import ConvertToDesktopModal from '../components/templates/ConvertToDesktopModal.vue'
import DeleteTemplateModal from '@/components/templates/DeleteTemplateModal.vue'
import { desktopStates } from '@/shared/constants'
import { mapActions, mapGetters } from 'vuex'
import { computed, ref, reactive } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  components: {
    IsardTable,
    AllowedModal,
    ConvertToDesktopModal,
    DeleteTemplateModal
  },
  setup (props, context) {
    const perPage = ref(10)
    const pageOptions = ref([10, 20, 30, 50, 100])
    const filterOn = reactive(['name', 'description'])

    const $store = context.root.$store
    $store.dispatch('fetchTemplates')
    $store.dispatch('fetchAllowedTemplates', 'shared')

    const templateId = computed(() => $store.getters.getId)

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'domains', id: templateId.value, allowed: allowed })
    }

    const currentTab = computed(() => $store.getters.getCurrentTab)

    const updateCurrentTab = (currentTab) => {
      $store.dispatch('updateCurrentTab', currentTab)
    }

    const rowClass = (item, type) => {
      if (!item || type !== 'row') return
      if (item.status.toLowerCase() === desktopStates.failed) return 'list-red-bar'
      if (item.needsBooking) return 'list-orange-bar'
    }

    const fields = [
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
        key: 'desktopSize',
        sortable: true,
        label: i18n.t('views.templates.table-header.template-size'),
        thStyle: { width: '35%' }
      },
      {
        key: 'actions',
        label: i18n.t('views.templates.table-header.actions'),
        thStyle: { width: '5%' }
      }
    ]
    const sharedFields = [
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
    ]

    const onClickGoToEditTemplate = (templateId) => {
      $store.dispatch('goToEditDomain', templateId)
    }

    const showAllowedModal = (template) => {
      $store.dispatch('fetchAllowed', { table: 'domains', id: template.id })
    }

    const showConvertToDesktopModal = (template) => {
      $store.dispatch('fetchConvertToDesktop', { template: template })
    }

    const enabledClass = (template) => {
      return template.enabled ? 'btn-blue' : 'btn-grey'
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

    const toggleEnabledIcon = (template) => {
      return template.enabled ? 'eye-fill' : 'eye-slash-fill'
    }

    const showDeleteModal = (templateId) => {
      $store.dispatch('fetchTemplateDerivatives', { id: templateId })
    }

    return {
      desktopStates,
      perPage,
      pageOptions,
      filterOn,
      updateAllowed,
      currentTab,
      updateCurrentTab,
      rowClass,
      fields,
      sharedFields,
      onClickGoToEditTemplate,
      showAllowedModal,
      showConvertToDesktopModal,
      enabledClass,
      toggleEnabled,
      toggleEnabledIcon,
      showDeleteModal
    }
  },
  computed: {
    ...mapGetters([
      'getTemplates',
      'getTemplatesLoaded',
      'getSharedTemplates',
      'getSharedTemplatesLoaded'
    ]),
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    }
  },
  destroyed () {
    this.$store.dispatch('resetTemplatesState')
  },
  methods: {
    ...mapActions([
      'goToDuplicate'
    ]
    ),
    onClickGoToDuplicate (templateId) {
      this.goToDuplicate(templateId)
    }
  }
}
</script>
