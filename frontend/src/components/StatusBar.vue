<template>
  <div
    id="statusbar"
    class="px-0 px-lg-5 pl-2"
    style="min-height: 3.6rem;"
  >
    <b-container
      fluid
      class="px-0"
    >
      <b-navbar
        toggleable="lg"
        type="light"
        variant=""
      >
        <div class="separator" />
        <div class="d-flex flex-grow">
          <!-- Left aligned nav items-->
          <b-navbar-nav
            id="statusbar-content"
            class="flex-grow flex-row"
          >
            <!-- Back to recycle bin -->
            <b-navbar-nav
              v-if="checkLocation('recycleBins')"
              class="flex-grow flex-row"
            >
              <b-nav-item disabled>
                <span
                  v-if="maxTime === 0"
                  class="d-none d-lg-inline text-medium-gray"
                >{{ $t("components.statusbar.recycle-bins.immediately") }}</span>
                <span
                  v-else-if="maxTime !== 'null'"
                  class="d-none d-lg-inline text-medium-gray"
                >{{ `${$t("components.statusbar.recycle-bins.max-time", { time: maxTime })}` }}</span>
              </b-nav-item>
            </b-navbar-nav>
            <b-nav-item
              v-if="checkLocation('recycleBin')"
              href="#"
              @click="goToRecycleBins"
            >
              <div>
                <b-icon
                  icon="arrow-left"
                  aria-hidden="true"
                  class="text-medium-gray mr-2 mr-lg-2"
                />
                {{ $t("components.statusbar.recycle-bin.back") }}
              </div>
            </b-nav-item>
            <!-- Back to deployments -->
            <b-nav-item
              v-if="checkLocation('deployment_desktops')"
              href="#"
              @click="goToDeployments"
            >
              <div>
                <b-icon
                  icon="arrow-left"
                  aria-hidden="true"
                  class="text-medium-gray mr-2 mr-lg-2"
                />
                {{ $t("components.statusbar.deployment.back") }}
              </div>
            </b-nav-item>
            <!-- Back to deployment desktop list -->
            <b-nav-item
              v-if="checkLocation('deployment_videowall')"
              href="#"
              @click="redirectDeployment"
            >
              <div>
                <b-icon
                  icon="arrow-left"
                  aria-hidden="true"
                  class="text-medium-gray mr-2 mr-lg-2"
                />
                {{ $t("components.statusbar.videowall.back") }}
              </div>
            </b-nav-item>
            <!-- filter -->
            <DesktopsFilter
              v-if="(checkLocation('desktops') || checkLocation('deployment_videowall')) && !creationMode"
              class="d-none d-lg-flex"
            />
            <!-- Only started checkbox -->
            <b-nav-item
              v-if="(checkLocation('desktops') || checkLocation('deployment_videowall')) && !creationMode"
              class="ml-2 ml-md-4"
              href="#"
              @click="startedFilter"
            >
              <div>
                <b-form-checkbox
                  id="started-checkbox"
                  v-model="started"
                  name="checkbox-1"
                  value="true"
                  unchecked-value="false"
                  aria-hidden="true"
                  class="mr-2 mr-lg-0"
                >
                  <p class="d-none d-md-inline p-0 m-0">
                    {{ $t("components.statusbar.checkbox-text") }}
                  </p>
                  <p class="d-inline d-md-none  p-0 m-0">
                    {{ $t("components.statusbar.checkbox-text-short") }}
                  </p>
                </b-form-checkbox>
              </div>
            </b-nav-item>
            <!-- Started count -->
            <b-nav-item
              v-if="(checkLocation('desktops') || checkLocation('deployment_videowall')) && !creationMode"
              disabled
              class="d-none d-md-inline ml-4"
            >
              <b-icon
                icon="display-fill"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0"
              />
            </b-nav-item>
            <b-nav-item
              v-if="(checkLocation('desktops') || checkLocation('deployment_videowall')) && !creationMode"
              disabled
            >
              <span class="d-none d-lg-inline text-medium-gray">{{ `${$t("components.statusbar.desktops-started")}:` }}</span><span class="text-medium-gray">{{ ` ${startedDesktops}` }}</span>
            </b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items-->
          <div class="pt-1">
            <b-button
              v-if="checkLocation('desktops') && !creationMode"
              :pill="true"
              class="mr-0 mr-md-4"
              variant="outline-primary"
              size="sm"
              @click="createDesktop()"
            >
              {{ `${$t("components.statusbar.new-desktop")}` }}
            </b-button>
          </div>
          <div class="pt-1">
            <b-button
              v-if="checkLocation('deployments') && !creationMode"
              :pill="true"
              class="mr-0 mr-md-4"
              variant="outline-primary"
              size="sm"
              @click="navigate('deploymentsnew')"
            >
              <DeploymentModal />
              {{ `${$t("components.statusbar.new-deployment")}` }}
            </b-button>
          </div>
          <div class="pt-1">
            <b-button
              v-if="checkLocation('media') && !creationMode"
              :pill="true"
              class="mr-0 mr-md-4"
              variant="outline-primary"
              size="sm"
              @click="createMedia()"
            >
              {{ `${$t("components.statusbar.new-media")}` }}
            </b-button>
          </div>
          <div
            v-if="checkLocation('deployment_desktops')"
            class="pt-1"
          >
            <!-- <b-button
              class="rounded-circle px-2 mr-2 btn-green"
              :title="$t('components.statusbar.deployment.buttons.start.title')"
              @click="startDesktops()"
            >
              <b-icon
                icon="play"
                scale="0.75"
              />
            </b-button> -->
            <DeploymentModal />
            <b-button
              class="rounded-circle px-2 mr-2 btn-red"
              :title="$t('components.statusbar.deployment.buttons.stop.title')"
              @click="stopDesktops()"
            >
              <b-icon
                icon="stop"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle px-2 mr-2"
              :class="visibleClass()"
              :title="deployment.visible ? $t('components.statusbar.deployment.buttons.make-not-visible.title') : $t('components.statusbar.deployment.buttons.make-visible.title')"
              @click="toggleVisible()"
            >
              <b-icon
                :icon="toggleVisibleIcon()"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle px-2 mr-2 btn-dark-blue"
              :title="$t('components.statusbar.deployment.buttons.videowall.title')"
              @click="goToVideowall()"
            >
              <b-icon
                icon="grid-fill"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle btn-purple px-2 mr-2"
              :title="$t('components.statusbar.deployment.buttons.download-direct-viewer.title')"
              @click="downloadDirectViewerCSV()"
            >
              <b-icon
                icon="download"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle px-2 mr-2 btn-orange"
              :title="$t('components.statusbar.deployment.buttons.recreate.title')"
              @click="recreateDeployment()"
            >
              <b-icon
                icon="arrow-clockwise"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle btn btn-blue px-2 mr-2"
              :title="$t('components.statusbar.deployment.buttons.edit.title')"
              @click="editDeployment()"
            >
              <b-icon
                icon="pencil-fill"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle px-2 mr-2 btn-dark-blue"
              :title="$t('components.statusbar.deployment.buttons.allowed.title')"
              @click="showAllowedModal()"
            >
              <b-icon
                icon="people-fill"
                scale="0.75"
              />
            </b-button>
            <AllowedModal @updateAllowed="updateUsers" />
            <b-button
              class="rounded-circle btn-red px-2 mr-2"
              :title="$t('components.statusbar.deployment.buttons.delete.title')"
              @click="deleteDeployment()"
            >
              <b-icon
                icon="x"
                scale="1"
              />
            </b-button>
          </div>
          <b-navbar-nav
            v-if="checkLocation('desktops') && !creationMode"
            class="ml-auto flex-row d-none d-xl-flex"
          >
            <b-nav-item
              href="#"
              :class="{selectedView: viewType === 'grid'}"
              @click="changeView('grid')"
            >
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
            <b-nav-item
              href="#"
              :class="{selectedView: viewType === 'list'}"
              class="ml-sm-2 ml-xl-0"
              @click="changeView('list')"
            >
              <b-icon
                icon="list-ul"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
          </b-navbar-nav>
          <!-- Videowall grid and individual view -->
          <b-navbar-nav
            v-if="checkLocation('deployment_videowall')"
            class="ml-auto flex-row d-none d-xl-flex"
          >
            <b-nav-item
              href="#"
              :class="{selectedView: viewType === 'grid'}"
              @click="changeView('grid')"
            >
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
            <b-nav-item
              href="#"
              :class="{selectedView: viewType === 'youtube'}"
              class="ml-sm-2 ml-xl-0"
              @click="changeView('youtube')"
            >
              <b-icon
                icon="grid1x2-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
          </b-navbar-nav>
          <!-- Recycle bin -->
          <b-navbar-nav
            v-if="!checkLocation('recycleBin') && !checkLocation('recycleBins')"
            class="ml-auto flex-row d-xl-flex"
          >
            <b-avatar
              button
              :badge="`${itemsInRecycleBin}`"
              badge-variant="danger"
              icon="trash"
              :title="$t('components.statusbar.recycle-bin.title')"
              aria-hidden="true"
              class="bg-lightgray text-medium-gray ml-2"
              @click="goToRecycleBins"
            />
          </b-navbar-nav>
          <b-navbar-nav
            v-if="checkLocation('recycleBin') && [user.user_id, 'system'].includes(recycleBin.agentId)"
            class="ml-auto flex-row d-xl-flex"
          >
            <RecycleBinModal />
            <b-button
              class="rounded-circle btn-green mr-2"
              :title="$t('components.statusbar.recycle-bin.buttons.restore.title')"
              @click="restoreRecycleBin()"
            >
              <b-icon
                icon="arrow-clockwise"
                scale="0.75"
              />
            </b-button>
            <b-button
              class="rounded-circle btn-red mr-2"
              :title="$t('components.statusbar.recycle-bin.buttons.delete.title')"
              @click="deleteRecycleBin()"
            >
              <b-icon
                icon="x"
                scale="1"
              />
            </b-button>
          </b-navbar-nav>
          <div class="pt-1">
            <b-button
              v-if="checkLocation('recycleBins')"
              :pill="true"
              class="mr-0 mr-md-4"
              variant="outline-danger"
              size="sm"
              @click="emptyRecycleBin()"
            >
              {{ `${$t("components.statusbar.recycle-bins.empty-recycle-bin")}` }}
            </b-button>
          </div>
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { desktopStates } from '@/shared/constants'
import AllowedModal from '@/components/AllowedModal.vue'
import DesktopsFilter from '@/components/desktops/DesktopsFilter.vue'
import DeploymentModal from '@/components/deployments/DeploymentModal.vue'
import RecycleBinModal from '@/components/recycleBin/RecycleBinModal.vue'
import { ref, computed, watch } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  components: {
    DesktopsFilter,
    DeploymentModal,
    AllowedModal,
    RecycleBinModal
  },
  setup (props, context) {
    const $store = context.root.$store

    const started = ref(false)

    const createDesktop = () => {
      $store.dispatch('checkCreateQuota', { itemType: 'desktops', routeName: 'desktopsnew' })
    }

    const createMedia = () => {
      $store.dispatch('checkCreateQuota', { itemType: 'media', routeName: 'medianew' })
    }

    $store.dispatch('fetchItemsInRecycleBin')

    const deployment = computed(() => $store.getters.getDeployment)
    const desktops = computed(() => $store.getters.getDesktops)
    const viewType = computed(() => $store.getters.getViewType)
    const recycleBin = computed(() => $store.getters.getRecycleBin)
    const user = computed(() => $store.getters.getUser)
    const maxTime = computed(() => $store.getters.getMaxTime)
    const itemsInRecycleBin = computed(() => $store.getters.getItemsInRecycleBin)

    const goToDeployments = () => {
      context.root.$router.push({ name: 'deployments' })
    }

    const goToRecycleBins = () => {
      context.root.$router.push({ name: 'recycleBins' })
    }

    const urlTokens = computed(() => $store.getters.getUrlTokens)

    const creationMode = computed(() => urlTokens.value.includes('new'))

    const checkLocation = (location) => {
      const tokens = urlTokens.value
      return tokens === location
    }

    const startedDesktops = computed(() => {
      const allDesktops = checkLocation('desktops') ? desktops.value : deployment.value.desktops
      const startedDesktops = allDesktops.filter((item) => {
        return item && [desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(item.state.toLowerCase())
      })
      return startedDesktops.length
    })

    // Deployment buttons
    const startDesktops = () => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('startDeploymentDesktops', { id: deployment.value.id })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.start-deployment-desktops', { name: deployment.value.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const stopDesktops = () => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('stopDeploymentDesktops', { id: deployment.value.id })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.stop-deployment-desktops', { name: deployment.value.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const redirectDeployment = () => {
      context.root.$router.push({ name: 'deployment_desktops', params: { id: deployment.value.id } })
    }

    const visibleClass = () => {
      return deployment.value.visible ? 'btn-blue' : 'btn-grey'
    }

    const toggleVisibleIcon = () => {
      return deployment.value.visible ? 'eye-fill' : 'eye-slash-fill'
    }

    const goToVideowall = () => {
      context.root.$router.push({ name: 'deployment_videowall', params: { id: deployment.value.id } })
    }

    const toggleVisible = () => {
      $store.dispatch('updateDeploymentModal', {
        show: true,
        type: 'visibility',
        color: 'blue',
        item: { id: deployment.value.id, name: deployment.value.name, visible: deployment.value.visible, stopStartedDomains: false }
      })
    }

    const downloadDirectViewerCSV = () => {
      $store.dispatch('updateDeploymentModal', {
        show: true,
        type: 'downloadCSV',
        color: 'purple',
        item: { id: deployment.value.id, name: deployment.value.name }
      })
    }

    const showAllowedModal = () => {
      $store.dispatch('fetchAllowed', { table: 'deployments', id: deployment.value.id })
    }

    const updateUsers = (allowed) => {
      $store.dispatch('editDeploymentUsers', { id: deployment.value.id, allowed: allowed })
    }

    const editDeployment = () => {
      $store.dispatch('goToEditDeployment', deployment.value.id)
    }

    const deleteDeployment = () => {
      $store.dispatch('updateDeploymentModal', {
        show: true,
        type: 'delete',
        color: 'red',
        item: { id: deployment.value.id, name: deployment.value.name }
      })
    }

    const recreateDeployment = () => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('recreateDeployment', { id: deployment.value.id })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.recreate-deployment', { name: deployment.value.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const startedFilter = () => {
      started.value = !started.value
      if (checkLocation('desktops')) {
        $store.dispatch('toggleShowStarted')
      } else if (checkLocation('deployment_videowall')) {
        $store.dispatch('toggleDeploymentsShowStarted')
      }
    }
    const changeView = (type) => {
      $store.dispatch('setViewType', type)
    }

    watch(() => context.root.$route, () => {
      started.value = false
      $store.dispatch('setViewType', 'grid')
    }, { immediate: true })

    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }

    // Recycle Bin
    const restoreRecycleBin = () => {
      $store.dispatch('updateRecycleBinModal', {
        show: true,
        type: 'restore',
        item: {
          id: recycleBin.value.id
        }
      })
    }

    const deleteRecycleBin = () => {
      $store.dispatch('updateRecycleBinModal', {
        show: true,
        type: 'delete',
        item: {
          id: recycleBin.value.id
        }
      })
    }

    const emptyRecycleBin = () => {
      $store.dispatch('updateRecycleBinModal', {
        show: true,
        type: 'empty',
        item: {
          id: recycleBin.value.id
        }
      })
    }

    return {
      goToDeployments,
      startDesktops,
      stopDesktops,
      deployment,
      visibleClass,
      toggleVisibleIcon,
      redirectDeployment,
      goToVideowall,
      toggleVisible,
      downloadDirectViewerCSV,
      showAllowedModal,
      updateUsers,
      editDeployment,
      deleteDeployment,
      recreateDeployment,
      createDesktop,
      createMedia,
      started,
      checkLocation,
      changeView,
      startedFilter,
      startedDesktops,
      creationMode,
      navigate,
      viewType,
      goToRecycleBins,
      restoreRecycleBin,
      deleteRecycleBin,
      recycleBin,
      user,
      maxTime,
      itemsInRecycleBin,
      emptyRecycleBin
    }
  }
}
</script>
