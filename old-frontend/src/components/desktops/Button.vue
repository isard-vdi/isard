<template>
  <!-- TODO: change spinnerActive to clickActive -->
  <b-button
    v-b-tooltip="{ title: tooltip || '', placement: 'top', customClass: 'isard-tooltip', trigger: 'hover', disabled: !tooltip }"
    :disabled="!active && !blocked"
    size="md"
    class="rounded-pill pt-2 rdp-progress-host"
    :class="[buttonClass, { 'btn-blocked': !active && blocked }]"
    :aria-disabled="!active ? 'true' : undefined"
    @click="active ? $emit('buttonClicked') : blocked && $emit('blockedClicked')"
  >
    <span
      v-if="progress !== undefined && progress !== null"
      class="rdp-progress"
      :class="`rdp-progress--${progressTone || 'wait'}`"
      :style="{ width: progress + '%' }"
      role="progressbar"
      :aria-valuenow="progress"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuetext="tooltip || ''"
      :aria-label="tooltip || ''"
    />
    <b-icon
      v-if="iconName !== '' && iconName !== undefined"
      class="mb-0 rdp-above"
      :icon="iconName"
    /><span class="ml-1 rdp-above">{{ buttText }}</span>
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
    tooltip: String,
    // RDP readiness fill: how far the check has got (0-100) and its tone, so
    // the button background fills left to right as each step passes.
    progress: Number,
    progressTone: String
  }
}
</script>

<style scoped>
.btn-blocked {
  opacity: 0.65;
  cursor: not-allowed;
}
.rdp-progress-host {
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
  border-radius: inherit;
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
