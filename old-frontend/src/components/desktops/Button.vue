<template>
  <!-- TODO: change spinnerActive to clickActive -->
  <b-button
    :disabled="!active"
    size="md"
    class="rounded-pill pt-2"
    :class="[buttonClass]"
    @click="active && $emit('buttonClicked')"
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
    iconName: String
  }
}
</script>
