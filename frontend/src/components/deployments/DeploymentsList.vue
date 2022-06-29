<template>
  <div class='table-list px-5'>
    <b-container fluid class='px-0'>
      <b-skeleton-wrapper :loading="loading" class='pb-1 pt-4 justify-content-start'>
        <template #loading>
          <b-col>
            <list-item-skeleton class="mb-2"></list-item-skeleton>
            <list-item-skeleton class="mb-2"></list-item-skeleton>
            <list-item-skeleton class="mb-2"></list-item-skeleton>
            <list-item-skeleton class="mb-2"></list-item-skeleton>
          </b-col>
        </template>
      <b-row class="scrollable-div">
        <b-col
          cols='12'
          class='d-flex flex-row flex-wrap justify-content-start'
        >
          <b-table :items='deployments' :fields='fields' :tbody-tr-class="rowClass" :responsive="true" @row-clicked="redirectDeployment">
            <template #cell(visible)='data'>
              <p class='text-dark-gray m-0 text-center'>
                <b-badge :variant="data.item.visible ? 'success' : 'danger'">{{ data.item.visible ? $t('views.deployment.visibility.visible') : $t('views.deployment.visibility.not-visible') }}</b-badge>
              </p>
            </template>
            <template #cell(name)='data'>
              <p class='m-0 font-weight-bold'>
                {{ data.item.name }}
              </p>
            </template>
            <template #cell(description)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.description }}
              </p>
            </template>
            <template #cell(startedDesktops)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.startedDesktops }} / {{ data.item.totalDesktops }}
              </p>
            </template>
            <template #cell(actions)='data'>
              <div class='d-flex justify-content-center align-items-center'>
                <b-button v-if="data.item.needsBooking" class="rounded-circle btn-orange px-2 mr-2" @click="onClickBookingDesktop(data.item)">
                  <b-icon icon="calendar" scale="0.75"></b-icon>
                </b-button>
                <b-button class="rounded-circle btn btn-red px-2 mr-2" @click="deleteDeployment(data.item)" :title="$t('components.statusbar.deployment.buttons.delete.title')">
                  <b-icon icon="trash-fill" scale="0.75"></b-icon>
                </b-button>
              </div>
            </template>
          </b-table>
          </b-col>
      </b-row>
      </b-skeleton-wrapper>
    </b-container>
  </div>
</template>
<script>
import i18n from '@/i18n'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'

export default {
  setup (props, context) {
    const $store = context.root.$store

    const rowClass = (item, type) => {
      if (item && type === 'row') {
        if (item.visible === true) {
          return 'cursor-pointer visibleHighlight'
        } else {
          return 'cursor-pointer'
        }
      } else {
        return null
      }
    }

    const redirectDeployment = (item) => {
      context.root.$router.push({ name: 'deployment_desktops', params: { id: item.id } })
    }

    const deleteDeployment = (deployment) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('deleteDeployment', { id: deployment.id })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.delete-deployment', { name: deployment.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const onClickBookingDesktop = (deployment) => {
      const data = { id: deployment.id, type: 'deployment', name: deployment.name }
      $store.dispatch('goToItemBooking', data)
    }

    return {
      rowClass,
      redirectDeployment,
      deleteDeployment,
      onClickBookingDesktop
    }
  },
  components: { ListItemSkeleton },
  props: {
    deployments: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'visible',
          sortable: true,
          label: i18n.t('views.deployments.table-header.visible'),
          thStyle: { width: '5%' }
        },
        {
          key: 'name',
          sortable: true,
          label: i18n.t('views.deployments.table-header.name'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'description',
          sortable: true,
          label: i18n.t('views.deployments.table-header.description'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'desktopName',
          sortable: true,
          label: i18n.t('views.deployments.table-header.desktop-name'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'template',
          sortable: true,
          label: i18n.t('views.deployments.table-header.template'),
          thStyle: { width: '20%' },
          tdClass: 'name'
        },
        {
          key: 'startedDesktops',
          sortable: true,
          label: i18n.t('views.deployments.table-header.started-desktops'),
          thStyle: { width: '35%' }
        },
        {
          key: 'actions',
          label: i18n.t('views.deployments.table-header.actions'),
          thStyle: { width: '5%' }
        }
      ]
    }
  }
}
</script>
