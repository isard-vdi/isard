<template>
<!-- TODO: change spinnerActive to clickActive -->
  <b-button
      :disabled="!active"
      @click="active && $emit('buttonClicked')"
      size='md'
      class='rounded-pill pt-2'
      :class="[buttColor]">
      <b-icon class="mb-0" v-if="iconName !== '' && iconName !== undefined" :icon="iconName"></b-icon><span class="ml-1">{{ buttText }}</span>
  </b-button>
</template>

<script>
export default {
  props: {
    spinnerActive: Boolean,
    buttColor: String,
    buttText: String,
    active: Boolean,
    iconName: String
  }
}
</script>
