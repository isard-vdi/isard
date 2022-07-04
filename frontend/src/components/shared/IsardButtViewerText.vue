<template>
  <i18n path="views.select-template.viewer">
    <template #name>
      {{ $t(`views.select-template.viewer-name.${viewerName}`) }}
    </template>
  </i18n>
</template>

<script>
export default {
  props: {
    viewerName: String
  }
}
</script>
