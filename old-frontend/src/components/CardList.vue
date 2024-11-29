<template>
  <b-container
    fluid
    class="card-list px-5"
  >
    <h5 class="font-weight-bold">
      {{ listTitle }}
    </h5>
    <b-row class="pb-3 pt-2">
      <b-col
        cols="12"
        md="auto"
        class="card-body pb-1 pt-4 d-flex flex-row flex-wrap justify-content-start"
      >
        <b-skeleton-wrapper
          :loading="loading"
          class="card-body pt-4 d-flex flex-row flex-wrap justify-content-start"
        >
          <template #loading>
            <card-skeleton />
            <card-skeleton />
            <card-skeleton />
          </template>
          <Card
            v-for="desktop in desktops"
            :key="desktop.id"
            :desktop="desktop"
            :templates="templates"
            :bastions="bastions"
          />
        </b-skeleton-wrapper>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import Card from '@/components/Card.vue'
import CardSkeleton from '@/components/CardSkeleton.vue'

export default {
  components: {
    Card,
    CardSkeleton
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
    bastions: {
      required: false,
      type: Array
    },
    persistent: {
      required: true,
      type: Boolean
    },
    loading: {
      required: true,
      type: Boolean
    }
  }
}
</script>
