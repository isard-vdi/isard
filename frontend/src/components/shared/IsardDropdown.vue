<template>
  <b-dropdown
        :disabled="ddDisabled"
        :variant="!(waitingIp && needsIp(defaultViewer)) ? variant : 'secondary'"
        :class="cssClass"
        split
        @click="defaultViewer && !(waitingIp && needsIp(defaultViewer)) && $emit('dropdownClicked', {desktopId: desktop.id, viewer: defaultViewer})">
        <template #button-content><div :title="fullViewerText" class="dropdown-default-text">{{ viewerText }}</div> <b-spinner v-if="defaultViewer && (waitingIp && needsIp(defaultViewer))" small type="grow"/>   </template>
                  <b-dropdown-item class="dropdown-text"
                    v-for="dkpviewer in viewers"
                    :disabled="waitingIp && needsIp(dkpviewer)"
                    :key="dkpviewer"
                    @click="$emit('dropdownClicked', {desktopId: desktop.id, viewer: dkpviewer, template: template || null})"
                  >
                  <isard-butt-viewer-text :viewerName="dkpviewer"></isard-butt-viewer-text>
                  <b-spinner v-if="waitingIp && needsIp(dkpviewer)" small type="grow"/>
                  </b-dropdown-item>
                </b-dropdown>
</template>

<script>
import i18n from '@/i18n'
import IsardButtViewerText from './IsardButtViewerText.vue'

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
    ddDisabled: Boolean
  },
  methods: {
    getViewerText (viewer) {
      const name = i18n.t(`views.select-template.viewer-name.${viewer}`)
      return i18n.t('views.select-template.viewer', i18n.locale, { name: name })
    },
    needsIp (viewer) {
      return ['rdp', 'rdp-html5'].includes(viewer)
    }
  }
}
</script>

<style scoped>
.item-inactive{
  background-color: blue;
}
</style>
