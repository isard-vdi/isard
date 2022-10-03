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
            <!-- Back -->
            <b-nav-item
              v-if="locationDeployment"
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
            <!-- filter -->
            <DesktopsFilter
              v-if="locationDesktops && !creationMode"
              class="d-none d-lg-flex"
            />
            <!-- Only started checkbox -->
            <b-nav-item
              v-if="locationDesktops && !creationMode"
              class="ml-2 ml-md-4"
              href="#"
              @click="toggleDesktopsFilter"
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
              v-if="locationDesktops && !creationMode"
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
              v-if="locationDesktops && !creationMode"
              disabled
            >
              <span class="d-none d-lg-inline text-medium-gray">{{ `${$t("components.statusbar.desktops-started")}:` }}</span><span class="text-medium-gray">{{ ` ${startedDesktops}` }}</span>
            </b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items-->
          <div class="pt-1">
            <b-button
              v-if="locationDesktops && !creationMode"
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
              v-if="locationDeployments && !creationMode"
              :pill="true"
              class="mr-0 mr-md-4"
              variant="outline-primary"
              size="sm"
              @click="navigate('deploymentsnew')"
            >
              {{ `${$t("components.statusbar.new-deployment")}` }}
            </b-button>
          </div>
          <div class="pt-1">
            <b-button
              v-if="locationMedia && !creationMode"
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
            v-if="locationDeployment"
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
              class="rounded-circle btn-red px-2 mr-2"
              :title="$t('components.statusbar.deployment.buttons.delete.title')"
              @click="deleteDeployment()"
            >
              <b-icon
                icon="trash-fill"
                scale="0.75"
              />
            </b-button>
          </div>
          <b-navbar-nav
            v-if="locationDesktops && !creationMode"
            class="ml-auto flex-row d-none d-xl-flex"
          >
            <b-nav-item
              href="#"
              :class="{selectedView: getViewType === 'grid'}"
              @click="setViewType('grid')"
            >
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
            <b-nav-item
              href="#"
              :class="{selectedView: getViewType === 'list'}"
              class="ml-sm-2 ml-xl-0"
              @click="setViewType('list')"
            >
              <b-icon
                icon="list"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              />
            </b-nav-item>
          </b-navbar-nav>
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { desktopStates } from '@/shared/constants'
import { mapActions, mapGetters } from 'vuex'
import DesktopsFilter from '@/components/desktops/DesktopsFilter.vue'
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  components: {
    DesktopsFilter
  },
  setup (props, context) {
    const $store = context.root.$store

    const createDesktop = () => {
      $store.dispatch('checkCreateDesktopQuota')
    }

    const createMedia = () => {
      $store.dispatch('checkCreateMediaQuota')
    }

    const deployment = computed(() => $store.getters.getDeployment)

    const goToDeployments = () => {
      context.root.$router.push({ name: 'deployments' })
    }

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
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('toggleVisible', { id: deployment.value.id, visible: deployment.value.visible })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t(deployment.value.visible ? 'messages.confirmation.not-visible-deployment' : 'messages.confirmation.visible-deployment', { name: deployment.value.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    const downloadDirectViewerCSV = () => {
      context.root.$snotify.clear()

      const resetJumperUrls = () => {
        context.root.$snotify.clear()
        $store.dispatch('downloadDirectViewerCSV', { id: deployment.value.id, reset: true })
      }

      const downloadCsv = () => {
        context.root.$snotify.clear()
        $store.dispatch('downloadDirectViewerCSV', { id: deployment.value.id })
      }

      context.root.$snotify.confirm(`${i18n.t('messages.confirmation.direct-viewer-reset')}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: resetJumperUrls, bold: true },
          { text: `${i18n.t('messages.no')}`, action: downloadCsv }
        ],
        placeholder: ''
      })
    }

    const deleteDeployment = () => {
      context.root.$snotify.clear()

      const yesAction = () => {
        context.root.$snotify.clear()
        $store.dispatch('deleteDeployment', { id: deployment.value.id }).then(() => {
          context.root.$router.push({ name: 'deployments' })
        })
      }

      const noAction = (toast) => {
        context.root.$snotify.clear()
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.delete-deployment', { name: deployment.value.name })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
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
      deleteDeployment,
      recreateDeployment,
      createDesktop,
      createMedia
    }
  },
  data () {
    return {
      started: false,
      showStarted: 'false'
    }
  },
  computed: {
    ...mapGetters([
      'getViewType',
      'getDesktops',
      'getUrlTokens'
    ]),
    startedDesktops () {
      const startedDesktops = this.getDesktops.filter((item) => {
        return item && [desktopStates.started, desktopStates.waitingip].includes(item.state.toLowerCase())
      })
      return startedDesktops.length
    },
    locationDesktops () {
      const tokens = this.getUrlTokens
      return tokens === 'desktops'
    },
    locationDeployments () {
      const tokens = this.getUrlTokens
      return tokens === 'deployments'
    },
    locationMedia () {
      const tokens = this.getUrlTokens
      return tokens === 'media'
    },
    locationDeployment () {
      const tokens = this.getUrlTokens
      return tokens === 'deployment_desktops'
    },
    creationMode () {
      return this.getUrlTokens.includes('new')
    }
  },
  methods: {
    ...mapActions([
      'setViewType',
      'toggleShowStarted',
      'navigate'
    ]),
    toggleDesktopsFilter () {
      this.started = !this.started
      this.toggleShowStarted()
    }
  }
}
</script>
