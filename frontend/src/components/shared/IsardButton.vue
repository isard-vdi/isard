<template>
  <b-button
      @click="!spinnerActive && $emit('buttonClicked')"
      :variant="spinnerActive ? '' : variant"
      :size="buttonSize ? buttonSize : ''"
      class="m-1">
        <isard-butt-viewer-text :viewerName="viewerName"></isard-butt-viewer-text>
        <b-spinner v-if="spinnerActive" small type="grow"/>
  </b-button>
</template>

<script>
import IsardButtViewerText from './IsardButtViewerText.vue'
export default {
  components: { IsardButtViewerText },
  props: {
    variant: String,
    viewerName: String,
    spinnerActive: Boolean,
    buttonSize: String
  }
}
</script>
