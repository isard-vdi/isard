<template>
    <b-container fluid class='card-list px-5'>
      <h5 class='font-weight-bold'>{{ listTitle }}</h5>

      <hr class='separator my-0' />

      <b-row class='pb-3 pt-2'>
        <b-col cols='12' md='auto' class='card-body pb-1 pt-4 d-flex flex-row flex-wrap justify-content-start'>
          <card v-for="desktop in desktops" :key="desktop.id" :desktop="desktop" :templates="templates"></card>
        </b-col>
      </b-row>
    </b-container>
</template>

<script>
import Card from '@/components/Card.vue'

export default {
  components: {
    Card
  },
  props: {
    listTitle: String,
    templates: {
      required: true,
      type: Array
    },
    desktops: {
      required: true,
      type: Array
    },
    persistent: {
      required: true,
      type: Boolean
    }
  }
}
</script>
