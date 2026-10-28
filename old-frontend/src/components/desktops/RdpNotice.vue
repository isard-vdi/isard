<template>
  <span
    v-b-tooltip="{ title: text, placement: 'top', customClass: 'isard-tooltip', trigger: 'hover focus' }"
    class="ml-2 flex-shrink-0 rdp-notice"
    :class="error ? 'rdp-notice--error' : 'rdp-notice--warn'"
    tabindex="0"
    role="img"
    :aria-label="text"
    data-testid="viewer-status-notice"
  >
    <b-icon :icon="error ? 'exclamation-triangle-fill' : 'exclamation-triangle'" />
  </span>
</template>

<script>
// A selected RDP viewer's warning or error: a triangle right of the viewer button, its text on hover.
export default {
  props: {
    text: String,
    error: Boolean
  }
}
</script>

<style scoped>
.rdp-notice {
  cursor: default;
}
.rdp-notice--error {
  color: #dc3545;
}
.rdp-notice--warn {
  color: #d9951a;
}
</style>
