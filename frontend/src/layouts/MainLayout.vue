<template>
  <div id="main-layout">
        <div class="header-wrapper">
          <NewNavBar/>
           <component v-bind:is="currentStatusBarComponent"></component>
        </div>
        <router-view></router-view>
  </div>
</template>

<script>
import { computed } from '@vue/composition-api'
import { sectionConfig } from '@/utils/section-config.js'
import NewNavBar from '@/components/NewNavBar.vue'
import StatusBar from '@/components/StatusBar.vue'
import ImagesStatusBar from '@/components/images/ImagesStatusBar.vue'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const urlTokens = computed(() => $store.getters.getUrlTokens)

    const section = computed(() => {
      const section = urlTokens.value.join('')
      return sectionConfig[section] !== undefined ? urlTokens.value.join('') : 'default'
    })

    const currentStatusBarComponent = computed(() => {
      return sectionConfig[section.value].statusBar
    })

    return {
      section,
      currentStatusBarComponent
    }
  },
  components: {
    StatusBar,
    NewNavBar,
    ImagesStatusBar
  }
}
</script>
