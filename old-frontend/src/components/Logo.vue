<template>
  <b-img
    id="logo"
    fluid-grow
    src="/custom/logo.svg"
    :alt="$t('components.title.logo-alt')"
    :style="styles"
    :class="classes"
  />
</template>

<script>
export default {
  props: {
    styles: String,
    classes: String
  }
}
</script>

<style scoped>
.logo-bg-circle {
  background-size: cover;
  background-repeat: no-repeat;
  background-position:center;
  background-color: #918e91;
  border-radius: 50%;
}
</style>
