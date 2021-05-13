<template>
  <b-dropdown
        :variant="variant"
        :class="cssClass"
        split
        :text="viewerText"
        @click="defaultViewer && $emit('dropdownClicked', {desktopId: desktop.id, viewer: defaultViewer})">
                  <b-dropdown-item
                    v-for="dkpviewer in viewers"
                    :key="dkpviewer"
                    @click="$emit('dropdownClicked', {desktopId: desktop.id, viewer: dkpviewer, template: template || null})"
                  >
                  <isard-butt-viewer-text :viewerName="dkpviewer"></isard-butt-viewer-text>
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
    defaultViewer: String,
    template: String
  },
  methods: {
    getViewerText (viewer) {
      const name = i18n.t(`views.select-template.viewer-name.${viewer}`)
      return i18n.t('views.select-template.viewer', i18n.locale, { name: name })
    }
  }
}
</script>
