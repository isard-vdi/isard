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
                <b-icon :icon="visibleIcon(data.item)" scale="1"></b-icon>
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
                <b-button class="rounded-circle px-2 mr-2 btn-purple" @click="goToVideowall(data.item)" :title="$t('views.deployments.buttons.videowall.title')">
                  <b-icon icon="grid-fill" scale="0.75"></b-icon>
                </b-button>
                <b-button class="rounded-circle px-2 mr-2" :class="visibleClass(data.item)"
                  @click="toggleVisible(data.item)"
                  :title="data.item.visible ? $t('views.deployments.buttons.make-not-visible.title') : $t('views.deployments.buttons.make-visible.title')"
                >
                  <b-icon :icon="toggleVisibleIcon(data.item)" scale="0.75"></b-icon>
                </b-button>
                <b-button class="rounded-circle px-2 mr-2 btn-green" @click="recreateDeployment(data.item)" :title="$t('views.deployments.buttons.recreate.title')">
                  <b-icon icon="arrow-clockwise" scale="0.75"></b-icon>
                </b-button>
                <b-button class="rounded-circle btn-orange px-2 mr-2" @click="downloadDirectViewerCSV(data.item)" :title="$t('views.deployments.buttons.download-direct-viewer.title')">
                  <b-icon icon="download" scale="0.75"></b-icon>
                </b-button>
                <b-button class="rounded-circle btn-red px-2 mr-2" @click="deleteDeployment(data.item)" :title="$t('views.deployments.buttons.delete.title')">
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

    const visibleClass = (deployment) => {
      return deployment.visible ? 'btn-grey' : 'btn-blue'
    }

    const visibleIcon = (deployment) => {
      return deployment.visible ? 'check' : 'x'
    }

    const toggleVisibleIcon = (deployment) => {
      return deployment.visible ? 'eye-slash-fill' : 'eye-fill'
    }

    const goToVideowall = (item) => {
      context.root.$router.push({ name: 'deployment_videowall', params: { id: item.id } })
    }

    const toggleVisible = (deployment) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        $store.dispatch('toggleVisible', { id: deployment.id })
        context.root.$snotify.clear()
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t(deployment.visible ? 'messages.confirmation.not-visible-deployment' : 'messages.confirmation.visible-deployment', { name: deployment.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const downloadDirectViewerCSV = (deployment) => {
      $store.dispatch('downloadDirectViewerCSV', { id: deployment.id })
    }

    const deleteDeployment = (deployment) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        $store.dispatch('deleteDeployment', { id: deployment.id })
        context.root.$snotify.clear()
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

    const recreateDeployment = (deployment) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        $store.dispatch('recreateDeployment', { id: deployment.id })
        context.root.$snotify.clear()
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.recreate-deployment', { name: deployment.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    return {
      rowClass,
      visibleClass,
      visibleIcon,
      toggleVisibleIcon,
      redirectDeployment,
      goToVideowall,
      toggleVisible,
      downloadDirectViewerCSV,
      deleteDeployment,
      recreateDeployment
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
          thStyle: { width: '25%' },
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
