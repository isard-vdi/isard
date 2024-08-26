<template>
  <b-row>
    <b-col
      v-if="title"
      cols="12"
      md="8"
      class="text-left"
    >
      <h6 class="font-weight-bold mt-4">
        {{ title }}
      </h6>
    </b-col>
    <b-col
      v-if="title"
      cols="12"
      md="4"
      class="text-right"
    >
      <h6 class="mt-4">
        {{ value }} / {{ max === false ? '&infin;' : max }}
      </h6>
    </b-col>
    <b-col cols="12">
      <b-progress
        :max="max === false ? 9999 : max"
        animated
      >
        <b-progress-bar
          v-if="value * 100 / max <= 75"
          variant="primary"
          :value="value"
        />
        <b-progress-bar
          v-else-if="value * 100 / max <= 90"
          variant="warning"
          :value="value"
        />
        <b-progress-bar
          v-else
          variant="danger"
          :value="value"
        />
      </b-progress>
    </b-col>
  </b-row>
</template>

<script>
export default {
  props: {
    title: {
      required: false,
      type: [String, Boolean],
      default: false
    },
    value: {
      required: true,
      type: Number,
      default: 0
    },
    max: {
      required: true,
      type: [Number, Boolean],
      default: false
    }
  }
}
</script>
