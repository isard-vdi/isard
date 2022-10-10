<template>
  <div id="main-layout">
    <div class="header-wrapper">
      <NewNavBar />
      <component :is="currentStatusBarComponent" />
    </div>
    <router-view />
  </div>
</template>

<script>
import { computed } from '@vue/composition-api'
import { sectionConfig } from '@/utils/section-config.js'
import NewNavBar from '@/components/NewNavBar.vue'
import StatusBar from '@/components/StatusBar.vue'
import BookingStatusBar from '@/components/booking/BookingStatusBar.vue'

export default {
  components: {
    StatusBar,
    NewNavBar,
    BookingStatusBar
  },
  setup (_, context) {
    const $store = context.root.$store

    const urlTokens = computed(() => $store.getters.getUrlTokens)

    const section = computed(() => {
      return sectionConfig[urlTokens.value] !== undefined ? urlTokens.value : 'default'
    })

    const currentStatusBarComponent = computed(() => {
      return sectionConfig[section.value].statusBar
    })

    return {
      section,
      currentStatusBarComponent
    }
  }
}
</script>
