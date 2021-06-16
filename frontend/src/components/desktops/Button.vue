<template>
<!-- TODO: change spinnerActive to clickActive -->
  <b-button
      :disabled="!active"
      @click="active && !spinnerActive && $emit('buttonClicked')"
      size='sm'
      class='px-4 rounded-pill ml-3'
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
