<template>
  <b-container
    id="content"
    fluid
  >
    <div v-if="storage_loaded && getStorage.length === 0">
      <h3><strong>{{ $t('views.storage.no-storage.title') }}</strong></h3>
      <p>{{ $t('views.storage.no-storage.subtitle') }}</p>
    </div>
    <StorageList
      v-else
      :storage="getStorage"
      :loading="!(storage_loaded)"
    />
  </b-container>
</template>

<script>
import StorageList from '@/components/StorageList.vue'
import { mapGetters } from 'vuex'

export default {
  components: {
    StorageList
  },
  computed: {
    ...mapGetters(['getStorage']),
    storage_loaded () {
      return this.$store.getters.getStorageLoaded
    },
    ...mapGetters(['getQuota'])
  },
  created () {
    this.$store.dispatch('fetchStorage')
    this.$store.dispatch('fetchAppliedQuota')
  },
  destroyed () {
    this.$store.dispatch('resetStorageState')
  }
}
</script>
