<template>
  <div id="statusbar" class="px-0 px-lg-5 pl-2" style="min-height: 3.6rem;">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="light" variant="">
        <div class="separator"></div>
        <div class="d-flex flex-grow">
           <!-- Left aligned nav items-->
          <b-navbar-nav id="statusbar-content" class="flex-grow flex-row">
            <!-- filter -->
            <DesktopsFilter v-if="locationDesktops && !creationMode" class="d-none d-lg-flex"></DesktopsFilter>
            <!-- Only started checkbox -->
            <b-nav-item v-if="locationDesktops && !creationMode" class="ml-2 ml-md-4" href="#" @click="toggleDesktopsFilter">
              <div>
                <b-form-checkbox
                  id="started-checkbox"
                  name="checkbox-1"
                  v-model="status"
                  value=true
                  unchecked-value=false
                  aria-hidden="true"
                  class="mr-2 mr-lg-0">
                    <p class="d-none d-md-inline p-0 m-0">{{$t("components.statusbar.checkbox-text")}}</p>
                    <p class="d-inline d-md-none  p-0 m-0">{{$t("components.statusbar.checkbox-text-short")}}</p>
                </b-form-checkbox>
              </div>
            </b-nav-item>
            <!-- Started count -->
            <b-nav-item v-if="locationDesktops && !creationMode"  disabled class="d-none d-md-inline ml-4">
              <b-icon
                icon="display-fill"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0">
              </b-icon>
            </b-nav-item>
            <b-nav-item v-if="locationDesktops && !creationMode" disabled><span class="d-none d-lg-inline text-medium-gray">{{`${$t("components.statusbar.desktops-started")}:`}}</span><span class="text-medium-gray">{{ ` ${startedDesktops}` }}</span></b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items-->
          <div class="pt-1"><b-button v-if="locationDesktops && !creationMode" :pill="true" class="mr-0 mr-md-4" variant="outline-primary" size="sm" @click="navigate('NewDesktop')">{{`${$t("components.statusbar.new-desktop")}`}}</b-button></div>
          <b-navbar-nav v-if="locationDesktops && !creationMode" class="ml-auto flex-row d-none d-xl-flex">
            <b-nav-item href="#" @click="setViewType('grid')" :class="{selectedView: getViewType === 'grid'}">
              <b-icon
                icon="grid-fill"
                aria-hidden="true"
                class="text-medium-gray mt-1"
              ></b-icon>
            </b-nav-item>
            <b-nav-item href="#" @click="setViewType('list')" :class="{selectedView: getViewType === 'list'}" class="ml-sm-2 ml-xl-0">
              <b-icon
                icon="list"
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
import { desktopStates } from '@/shared/constants'
import { mapActions, mapGetters } from 'vuex'
import DesktopsFilter from '@/components/desktops/DesktopsFilter.vue'

export default {
  components: {
    DesktopsFilter
  },
  data () {
    return {
      status: false,
      showStarted: 'false'
    }
  },
  methods: {
    ...mapActions([
      'setViewType',
      'toggleShowStarted',
      'navigate'
    ]),
    toggleDesktopsFilter () {
      this.status = !this.status
      this.toggleShowStarted()
    }
  },
  computed: {
    ...mapGetters([
      'getViewType',
      'getDesktops',
      'getUrlTokens'
    ]),
    startedDesktops () {
      const startedDesktops = this.getDesktops.filter((item) => {
        return item && item.state.toLowerCase() === desktopStates.started
      })
      return startedDesktops.length
    },
    locationDesktops () {
      const tokens = this.getUrlTokens
      return tokens.includes('desktops')
    },
    creationMode () {
      return this.getUrlTokens.includes('new')
    }
  }
}
</script>
