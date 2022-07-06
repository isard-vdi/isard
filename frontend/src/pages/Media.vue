<template>
  <b-container
    id="content"
    fluid
  >
    <div v-if="getMediaLoaded && getMedia.length === 0">
      <h3><strong>{{ $t('views.media.no-media.title') }}</strong></h3>
      <p>{{ $t('views.media.no-media.subtitle') }}</p>
    </div>
    <MediaList
      v-else
      :media="getMedia"
      :loading="!(getMediaLoaded)"
    />
  </b-container>
</template>
<script>
import MediaList from '@/components/media/MediaList.vue'
import { mapGetters } from 'vuex'

export default {
  components: {
    MediaList
  },
  setup (_, context) {
    const $store = context.root.$store
    $store.dispatch('fetchMedia')
  },
  computed: {
    ...mapGetters([
      'getMedia',
      'getMediaLoaded'
    ])
  }
}
</script>
