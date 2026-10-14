<template>
  <b-dropdown
    :disabled="ddDisabled"
    :variant="!(waitingIp && needsIp(defaultViewer)) ? variant : 'secondary'"
    :class="cssClass"
    split
    @click="(defaultViewer && !(waitingIp && needsIp(defaultViewer))) ? $emit('dropdownClicked', {desktopId: desktop.id, viewer: defaultViewer}) : $emit('notifyWaitingIp')"
  >
    <template #button-content>
      <div
        v-b-tooltip="{ title: (statusText && needsIp(defaultViewer)) ? statusText : `${fullViewerText}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
        class="dropdown-default-text"
      >
        {{ viewerText }}
      </div>
      <b-icon
        v-if="defaultViewer && statusError && needsIp(defaultViewer)"
        icon="exclamation-triangle-fill"
        class="item-spinner rdp-status-error"
      />
      <b-spinner
        v-else-if="defaultViewer && (waitingIp && needsIp(defaultViewer))"
        small
        type="grow"
        class="item-spinner"
      />
    </template>
    <b-dropdown-item
      v-for="dkpviewer in viewers"
      :key="dkpviewer"
      v-b-tooltip="{ title: (statusText && needsIp(dkpviewer)) ? statusText : '', placement: 'left', customClass: 'isard-tooltip', trigger: 'hover', disabled: !(statusText && needsIp(dkpviewer)) }"
      class="dropdown-text"
      :link-class="{ 'text-muted': waitingIp && needsIp(dkpviewer) }"
      @click="(waitingIp && needsIp(dkpviewer)) ? $emit('notifyWaitingIp') : $emit('dropdownClicked', {desktopId: desktop.id, viewer: dkpviewer, template: template || null})"
    >
      <isard-butt-viewer-text :viewer-name="dkpviewer" />
      <b-icon
        v-if="statusError && needsIp(dkpviewer)"
        icon="exclamation-triangle-fill"
        class="item-spinner rdp-status-error"
      />
      <b-spinner
        v-else-if="waitingIp && needsIp(dkpviewer)"
        small
        type="grow"
        class="item-spinner"
      />
    </b-dropdown-item>
  </b-dropdown>
</template>

<script>
import i18n from '@/i18n'
import IsardButtViewerText from './IsardButtViewerText.vue'
import { DesktopUtils } from '@/utils/desktopsUtils'

export default {
  components: { IsardButtViewerText },
  props: {
    viewers: Array,
    cssClass: String,
    text: String,
    variant: String,
    desktop: Object,
    viewerText: String,
    fullViewerText: String,
    defaultViewer: String,
    template: String,
    waitingIp: Boolean,
    labelSize: String,
    ddDisabled: Boolean,
    // RDP step of the desktop: tooltip on the RDP viewers, and a warning icon
    // instead of the spinner when the guest refused
    statusText: String,
    statusError: Boolean
  },
  methods: {
    getViewerText (viewer) {
      return i18n.t(`views.select-template.viewer-name.${viewer}`)
    },
    needsIp (viewer) {
      return DesktopUtils.viewerNeedsIp(viewer)
    }
  }
}
</script>

<style scoped>
.item-inactive{
  background-color: blue;
}
.rdp-status-error {
  color: #dc3545;
}
</style>
