<template>
  <b-row>
    <b-col cols="12" md="8" class="text-left">
      <h6 class="font-weight-bold mt-4">{{ title }}</h6>
    </b-col>
    <b-col cols="12" md="4" class="text-right">
      <h6 class="mt-4">{{ value }} / {{ max }}</h6>
    </b-col>
    <b-col cols="12">
      <b-progress :value="value" :max="max" show-progress animated></b-progress>
    </b-col>
  </b-row>
</template>

<script>
export default {
  props: {
    title: {
      required: true,
      type: String,
      default: ''
    },
    value: {
      required: true,
      type: Number,
      default: 0
    },
    max: {
      required: true,
      type: Number,
      default: 0
    }
  }
}
</script>
