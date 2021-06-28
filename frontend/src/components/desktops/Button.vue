<template>
<!-- TODO: change spinnerActive to clickActive -->
  <b-button
      :disabled="!active"
      @click="active && !spinnerActive && $emit('buttonClicked')"
      size='sm'
      class='px-2 rounded-pill'
      :class="[buttColor]">
      {{ buttText }}
  </b-button>
</template>

<script>
export default {
  props: {
    spinnerActive: Boolean,
    buttColor: String,
    buttText: String,
    active: Boolean
  }
}
</script>
