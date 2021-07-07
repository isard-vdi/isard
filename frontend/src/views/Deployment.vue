<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
    </div>
    <b-container fluid id="content">
      <h1>Deployment {{ this.$route.params.id }}</h1>
    </b-container>
  </div>
</template>
<script>
// @ is an alias to /src
import NewNavBar from '@/components/NewNavBar.vue'

export default {
  components: {
    NewNavBar
  }
}
</script>
