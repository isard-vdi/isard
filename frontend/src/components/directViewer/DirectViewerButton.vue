<template>
  <b-col cols="12">
    <div class="bg-white rounded-15 py-4 px-4 text-center mb-4">
      <div
        style="height: 5rem; padding-top: 0.5rem"
        class="mb-4"
      >
        <img
          :src="require(`@/assets/img/icons/${getViewerData({kind: viewer.kind, protocol: viewer.protocol}).icon }.svg`)"
          alt=""
          style="max-inline-size: fit-content;"
        >
      </div>
      <div
        v-if="isWaiting(directViewer.state, viewer.kind + '-' + viewer.protocol)"
        class="ml-4 d-flex flex-row justify-left"
      >
        <b-spinner
          small
          variant="light"
          class="align-self-center mr-2 status-spinner"
        />
        <p class="mb-0 text-state font-weight-bold status-orange">
          {{ $t(`views.direct-viewer.waitingip`) }}
        </p>
      </div>
      <a
        v-if="viewer.protocol === 'spice'"
        v-b-modal.spice_help_modal
        href="#"
      >
        <p
          v-b-tooltip="{ title: `${$t('views.direct-viewer.help.spice.spice-help')}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
          class="h4 cursor-pointer"
          style="position:absolute; top: 1.5rem; right: 2.3rem;"
        >
          <b-icon
            size="lg"
            icon="question-circle-fill"
            variant="info"
          />
        </p>
      </a>
      <a
        v-if="viewer.protocol === 'rdpgw'"
        v-b-modal.rdp_help_modal
        href="#"
      >
        <p
          v-b-tooltip="{ title: `${$t('views.direct-viewer.help.rdp.rdp-help')}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
          class="h4 cursor-pointer"
          style="position:absolute; top: 1.5rem; right: 2.3rem;"
        >
          <b-icon
            size="lg"
            icon="question-circle-fill"
            variant="info"
          />
        </p>
      </a>
      <div class="description d-flex align-items-center justify-content-center">
        <small v-if="viewerDescription">
          {{ viewerDescription }}
        </small>
      </div>
      <b-button
        class="mt-2 w-100 direct-viewer-button"
        :disabled="isWaiting(directViewer.state, viewer.kind + '-' + viewer.protocol)"
        @click="openDirectViewerDesktop(viewer)"
      >
        {{ getViewerData({kind: viewer.kind, protocol: viewer.protocol}).buttonText }}
      </b-button>
    </div>
  </b-col>
</template>

<script>
import { desktopStates } from '@/shared/constants'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { mapActions } from 'vuex'
import i18n from '@/i18n'

export default {
  props: {
    viewer: {
      type: Object,
      required: true
    },
    directViewer: {
      type: Object,
      required: true
    },
    viewerDescription: {
      type: String,
      required: false
    }
  },
  data () {
    return {
      desktopStates
    }
  },
  methods: {
    ...mapActions(['openDirectViewerDesktop']),
    isWaiting (state, viewer) {
      return [desktopStates.waitingip].includes(state.toLowerCase()) && DesktopUtils.viewerNeedsIp(viewer)
    },
    getViewerData (payload) {
      const icons = {
        browser: {
          vnc: {
            icon: 'browser',
            buttonText: i18n.t('views.select-template.viewer-name.browser-vnc')
          },
          rdp: {
            icon: 'browser',
            buttonText: i18n.t('views.select-template.viewer-name.browser-rdp')
          }
        },
        file: {
          spice: {
            icon: 'file',
            buttonText: i18n.t('views.select-template.viewer-name.file-spice')
          },
          rdpgw: {
            icon: 'file',
            buttonText: i18n.t('views.select-template.viewer-name.file-rdpgw')
          }
        }
      }
      return icons[payload.kind][payload.protocol]
    }
  }
}
</script>

<style scoped>
.direct-viewer-button {
  border-radius: 7px;
  font-size: 0.8rem;
  background-color: #97c277;
  border-color: #97c277;
  color: black;
  font-size: 1rem;
}

.description {
  height: 50px;
}
</style>
