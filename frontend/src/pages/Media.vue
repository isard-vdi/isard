<template>
  <b-container
    id="content"
    fluid
  >
    <b-tabs>
      <b-tab
        :active="currentTab === 'media'"
        @click="updateCurrentTab('media')"
      >
        <template #title>
          <b-spinner
            v-if="!(getMediaLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.media.tabs.media-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.media.tabs.media') }}</span>
        </template>
        <template v-if="getMediaLoaded && getMedia.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.media.no-media.title') }}</strong></h3>
            <p>{{ $t('views.media.no-media.subtitle') }}</p>
          </div>
        </template>
        <template v-else>
          <MediaList
            :media="getMedia"
            :loading="!(getMediaLoaded)"
          />
        </template>
      </b-tab>
      <b-tab
        :active="currentTab === 'sharedMedia'"
        @click="updateCurrentTab('sharedMedia')"
      >
        <template #title>
          <b-spinner
            v-if="!(getSharedMediaLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.media.tabs.shared-media-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.media.tabs.shared-media') }}</span>
        </template>
        <template v-if="getSharedMediaLoaded && getSharedMedia.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.media.no-shared-media.title') }}</strong></h3>
            <p>{{ $t('views.media.no-shared-media.subtitle') }}</p>
          </div>
        </template>
        <template v-else>
          <MediaList
            :shared="true"
            :media="getSharedMedia"
            :loading="!(getSharedMediaLoaded)"
          />
        </template>
      </b-tab>
      <AllowedModal @updateAllowed="updateAllowed" />
    </b-tabs>
  </b-container>
</template>
<script>
import MediaList from '@/components/media/MediaList.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import { mapGetters, mapActions } from 'vuex'
import { computed } from '@vue/composition-api'

export default {
  components: {
    MediaList,
    AllowedModal
  },
  setup (_, context) {
    const $store = context.root.$store
    $store.dispatch('fetchMedia')
    $store.dispatch('fetchSharedMedia')

    const mediaId = computed(() => $store.getters.getId)

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'media', id: mediaId.value, allowed: allowed })
    }

    const currentTab = computed(() => $store.getters.getCurrentTab)

    return {
      currentTab,
      updateAllowed
    }
  },
  computed: {
    ...mapGetters([
      'getMedia',
      'getMediaLoaded',
      'getSharedMedia',
      'getSharedMediaLoaded'
    ])
  },
  destroyed () {
    this.$store.dispatch('resetMediaState')
  },
  methods: {
    ...mapActions([
      'updateCurrentTab'
    ])
  }
}
</script>
