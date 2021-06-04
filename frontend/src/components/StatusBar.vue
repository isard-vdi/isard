<template>
  <div id="statusbar" class="px-0 px-lg-5 pl-2">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="light" variant="">
        <div class="separator"></div>

        <div class="d-flex flex-grow">
          <b-navbar-nav id="statusbar-content" class="flex-grow flex-row">
            <b-nav-item href="#" disabled>
              <b-icon
                icon="display-fill"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0"
              ></b-icon>
            </b-nav-item>
            <!-- <b-nav-item href="#" class="mr-2 mr-lg-0">Desktops Creados: 85/100</b-nav-item> -->
            <b-nav-item><span class="d-none d-lg-inline">{{`${$t("components.statusbar.desktops-started")}:`}}</span>{{ ` ${startedDesktops}` }}</b-nav-item>
            <b-nav-item class="isard-navitem-margin" href="#" @click="toggleDesktopsFilter">
              <div>
                <b-form-checkbox
                  id="started-checkbox"
                  name="checkbox-1"
                  v-model="status"
                  value=true
                  unchecked-value=false
                  aria-hidden="true"
                  class="mr-2 mr-lg-0">
                    {{$t("components.statusbar.checkbox-text")}}
                </b-form-checkbox>
              </div>
            </b-nav-item>
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
import { desktopStates } from '@/shared/constants'

export default {
  data () {
    return {
      status: false,
      showStarted: 'false'
    }
  },
  methods: {
    changeView (type) {
      this.$store.dispatch('setViewType', type)
    },
    toggleDesktopsFilter () {
      this.status = !this.status
      this.$store.dispatch('toggleShowStarted')
    }
  },
  computed: {
    startedDesktops () {
      const startedDesktops = this.$store.getters.getDesktops.filter((item) => {
        return item && item.state.toLowerCase() === desktopStates.started
      })
      return startedDesktops.length
    },
    getShowStarted () {
      return this.$store.getters.getShowStarted
    }
  }
}
</script>
