<template>
  <div
    :class="[
      'p-col-12',
      'p-mb-2',
      'p-lg-' + (colspan || 3),
      'p-md-6',
      'p-mb-lg-0'
    ]"
  >
    <label>{{ label }}</label>
    <InputText v-bind="$attrs" />
  </div>
</template>
<script>
export default {
  props: {
    label: {
      type: String,
      required: true
    },
    colspan: {
      type: Number,
      required: true
    }
  }
};
</script>
<style scoped></style>
