<template>
  <div id="statusbar" class="px-0 px-lg-5 pl-2">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="light" variant="">
        <div class="separator"></div>
        <div class="d-flex flex-grow">

          <!-- Left aligned nav items-->
          <b-navbar-nav id="statusbar-content" class="flex-grow flex-row">
            <!-- Only started checkbox -->
            <b-nav-item class="ml-2 ml-md-4" href="#" @click="toggleStartedFilter">
              <div>
                <b-form-checkbox
                  id="started-checkbox"
                  name="checkbox-1"
                  v-model="started"
                  value=true
                  unchecked-value=false
                  aria-hidden="true"
                  class="mr-2 mr-lg-0">
                    <p class="d-none d-md-inline p-0 m-0">{{$t("components.statusbar.checkbox-text")}}</p>
                    <p class="d-inline d-md-none  p-0 m-0">{{$t("components.statusbar.checkbox-text-short")}}</p>
                </b-form-checkbox>
              </div>
            </b-nav-item>
          </b-navbar-nav>

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
import { mapActions, mapGetters } from 'vuex'

export default {
  data () {
    return {
      started: false
    }
  },
  methods: {
    ...mapActions([
      'toggleDeploymentsShowStarted'
    ]),
    changeView (type) {
      this.$store.dispatch('setViewType', type)
    },
    toggleStartedFilter () {
      this.started = !this.started
      this.toggleDeploymentsShowStarted()
    }
  },
  computed: {
    ...mapGetters(['getViewType'])
  }
}
</script>
