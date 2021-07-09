<template>
  <div id="statusbar" class="px-0 px-lg-5 pl-2">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="light" variant="">
        <div class="separator"></div>
        <div class="d-flex flex-grow">

          <!-- Right aligned nav items-->
          <b-navbar-nav class="ml-auto flex-row d-none d-xl-flex">

            <b-nav-item href="#" @click="changeView('grid')" :class="{selectedView: getViewType === 'grid'}">
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              ></b-icon>
            </b-nav-item>

            <b-nav-item href="#" @click="changeView('youtube')" :class="{selectedView: getViewType === 'youtube'}" class="ml-sm-2 ml-xl-0">
              <b-icon
                icon="grid1x2-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              ></b-icon>
            </b-nav-item>

          </b-navbar-nav>
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { mapGetters } from 'vuex'

export default {
  methods: {
    changeView (type) {
      this.$store.dispatch('setViewType', type)
    }
  },
  computed: {
    ...mapGetters(['getViewType'])
  }
}
</script>
