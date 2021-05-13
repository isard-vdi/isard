<template>
  <b-button
      @click="$emit('buttonClicked')"
      :variant="variant">
        <isard-butt-viewer-text :viewerName="viewerName"></isard-butt-viewer-text>
  </b-button>
</template>

<script>
import IsardButtViewerText from './IsardButtViewerText.vue'
export default {
  components: { IsardButtViewerText },
  props: {
    variant: String,
    cssclass: String,
    viewerName: String
  }
}
</script>
