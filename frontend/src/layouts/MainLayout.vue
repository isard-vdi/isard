<template>
  <div id="main-layout">
        <div class="header-wrapper">
          <NewNavBar/>
          <StatusBar/>
        </div>
        <router-view></router-view>
  </div>
</template>

<script>
import NewNavBar from '@/components/NewNavBar.vue'
import StatusBar from '@/components/StatusBar.vue'

export default {
  components: {
    StatusBar,
    NewNavBar
  }
}
</script>
