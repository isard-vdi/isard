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

    const currentRoute = computed(() => $store.getters.getCurrentRoute)

    const section = computed(() => {
      return sectionConfig[currentRoute.value] !== undefined ? currentRoute.value : 'default'
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
