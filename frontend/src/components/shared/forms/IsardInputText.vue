<template>
  <div
    :class="['p-col-12', 'p-mb-2', 'p-lg-' + colspan, 'p-md-6', 'p-mb-lg-0']"
  >
    <label>{{ label }}</label>
    <InputText v-bind="$attrs" />
  </div>
</template>
<script>
import InputText from 'primevue/inputtext';

export default {
  components: {
    InputText
  },
  props: {
    label: {
      type: String,
      required: true
    },
    colspan: {
      type: String,
      required: false,
      default: '3'
    }
  }
};
</script>
