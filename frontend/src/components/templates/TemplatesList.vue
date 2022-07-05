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
        <b-row class="scrollable-div">
          <b-col
            cols="12"
            class="d-flex flex-row flex-wrap justify-content-start"
          >
            <b-table
              :items="templates"
              :fields="fields"
              tbody-tr-class="cursor-pointer"
              :responsive="true"
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
                </div>
              </template>
            </b-table>
          </b-col>
        </b-row>
      </b-skeleton-wrapper>
      <AllowedModal @updateAllowed="updateAllowed" />
    </b-container>
  </div>
</template>
<script>
import i18n from '@/i18n'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import { computed } from '@vue/composition-api'

export default {
  components: { ListItemSkeleton, AllowedModal },
  props: {
    templates: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    }
  },
  setup (props, context) {
    const $store = context.root.$store

    const templateId = computed(() => $store.getters.getId)

    const showAllowedModal = (template) => {
      $store.dispatch('fetchAllowed', { table: 'domains', id: template.id })
    }

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'domains', id: templateId.value, allowed: allowed })
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

    return {
      showAllowedModal,
      updateAllowed,
      enabledClass,
      toggleEnabledIcon,
      toggleEnabled
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
      ]
    }
  }
}
</script>
