<template>
  <i18n :path="`views.select-template.viewer-name.${viewerName}`" />
</template>

<script>
export default {
  props: {
    viewerName: String
  }
}
</script>
