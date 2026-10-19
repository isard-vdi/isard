<template>
  <b-dropdown
    :disabled="ddDisabled"
    :variant="!(waitingIp && needsIp(defaultViewer)) ? variant : 'secondary'"
    :class="cssClass"
    class="rdp-progress-dd"
    split
    @click="(defaultViewer && !(waitingIp && needsIp(defaultViewer))) ? $emit('dropdownClicked', {desktopId: desktop.id, viewer: defaultViewer}) : $emit('notifyWaitingIp')"
  >
    <template #button-content>
      <span
        v-if="defaultViewer && statusProgress !== undefined && needsIp(defaultViewer)"
        class="rdp-progress"
        :class="`rdp-progress--${statusTone || 'wait'}`"
        :style="{ width: statusProgress + '%' }"
        role="progressbar"
        :aria-valuenow="statusProgress"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuetext="statusText || ''"
        :aria-label="statusText || ''"
      />
      <div
        v-b-tooltip="{ title: (statusText && needsIp(defaultViewer)) ? statusText : `${fullViewerText}`, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover' }"
        class="dropdown-default-text rdp-above"
      >
        {{ viewerText }}
      </div>
      <b-icon
        v-if="defaultViewer && statusError && needsIp(defaultViewer)"
        icon="exclamation-triangle-fill"
        class="item-spinner rdp-status-error rdp-above"
      />
      <b-icon
        v-else-if="defaultViewer && statusWarn && needsIp(defaultViewer)"
        icon="exclamation-triangle"
        class="item-spinner rdp-status-warn rdp-above"
      />
      <b-spinner
        v-else-if="defaultViewer && (waitingIp && needsIp(defaultViewer))"
        small
        type="grow"
        class="item-spinner rdp-above"
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
      <b-icon
        v-else-if="statusWarn && needsIp(dkpviewer)"
        icon="exclamation-triangle"
        class="item-spinner rdp-status-warn"
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
    // RDP step on the RDP viewers: tooltip, a warning icon (error/warn) and a progress fill.
    statusText: String,
    statusError: Boolean,
    statusWarn: Boolean,
    statusProgress: Number,
    statusTone: String
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
.rdp-status-warn {
  color: #d9951a;
}
/* Readiness fill on the split default button. The split button is rendered by
   bootstrap-vue, so reach it with a deep selector. */
.rdp-progress-dd::v-deep .btn {
  position: relative;
  overflow: hidden;
}
.rdp-progress {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 0;
  pointer-events: none;
  transition: width 0.3s ease;
}
.rdp-progress--wait {
  background-color: rgba(56, 189, 248, 0.4);
}
.rdp-progress--warn {
  background-color: rgba(251, 191, 36, 0.45);
}
.rdp-progress--error {
  background-color: rgba(248, 113, 113, 0.42);
}
.rdp-above {
  position: relative;
  z-index: 1;
}
</style>
