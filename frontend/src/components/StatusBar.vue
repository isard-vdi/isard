<template>
  <div id="statusbar" class="px-5">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="light" variant="">
        <div class="separator"></div>

        <div class="d-flex flex-grow">
          <b-navbar-nav class="flex-grow flex-row">
            <b-nav-item href="#" disabled>
              <b-icon
                icon="display-fill"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0"
              ></b-icon>
            </b-nav-item>
            <!-- <b-nav-item href="#" class="mr-2 mr-lg-0">Desktops Creados: 85/100</b-nav-item> -->
            <b-nav-item>Desktops Arrancados: {{ startedDesktops }}</b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items
          <b-navbar-nav class="ml-auto flex-row">

            <b-nav-item href="#" @click="changeView('grid')">
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0"
              ></b-icon>
            </b-nav-item>

            <b-nav-item href="#" @click="changeView('list')">
              <b-icon
                icon="list"
                aria-hidden="true"
                class="text-medium-gray"
              ></b-icon>
            </b-nav-item>

          </b-navbar-nav>-->
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { DesktopUtils } from '@/utils/desktopsUtils'
import { desktopStates } from '@/shared/constants'

export default {
  methods: {
    changeView (type) {
      this.$store.dispatch('setViewType', type)
    }
  },
  computed: {
    startedDesktops () {
      const startedDesktops = DesktopUtils.parseDesktops(this.$store.getters.getDesktops).filter((item) => {
        return item && item.state.toLowerCase() === desktopStates.started
      })
      return startedDesktops.length
    }
  }
}
</script>
