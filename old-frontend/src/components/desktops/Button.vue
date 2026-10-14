<template>
  <!-- TODO: change spinnerActive to clickActive -->
  <b-button
    v-b-tooltip="{ title: tooltip || '', placement: 'top', customClass: 'isard-tooltip', trigger: 'hover', disabled: !tooltip }"
    :disabled="!active && !blocked"
    size="md"
    class="rounded-pill pt-2"
    :class="[buttonClass, { 'btn-blocked': !active && blocked }]"
    :aria-disabled="!active ? 'true' : undefined"
    @click="active ? $emit('buttonClicked') : blocked && $emit('blockedClicked')"
  >
    <b-icon
      v-if="iconName !== '' && iconName !== undefined"
      class="mb-0"
      :icon="iconName"
    /><span class="ml-1">{{ buttText }}</span>
  </b-button>
</template>

<script>
export default {
  props: {
    spinnerActive: Boolean,
    buttonClass: String,
    buttText: String,
    active: [Boolean, String],
    iconName: String,
    // An inactive button that still answers a click/tap with ``blockedClicked``,
    // so touch screens (no hover tooltip) can be told why it is inactive.
    blocked: Boolean,
    tooltip: String
  }
}
</script>

<style scoped>
.btn-blocked {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>
