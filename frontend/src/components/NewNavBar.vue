<template>
  <div id="navbar" class="bg-darkgray px-0 px-lg-5 pl-4">
    <b-container fluid class="px-0">
      <b-navbar toggleable="lg" type="dark" variant="">
          <div id="logo-wrapper">
            <Logo/>
          </div>
        <b-navbar-toggle class="ml-auto" target="nav-collapse"></b-navbar-toggle>

        <b-collapse id="nav-collapse" is-nav>
          <b-navbar-nav id="left-side" class="mt-5 mt-lg-0">
            <b-nav-item :to="{ name: 'desktops' }">{{ $t("components.navbar.home") }}</b-nav-item>
            <b-nav-item v-if="getUser.role_id !== 'user'"  :to="{ name: 'templates' }">{{ $t("components.navbar.templates") }}</b-nav-item>
            <b-nav-item v-if="getUser.role_id === 'advanced'" :to="{ name: 'deployments' }">{{ $t("components.navbar.deployments") }}</b-nav-item>
            <b-nav-item href="#" @click="fetchVpn()">{{ $t("components.navbar.vpn.download") }}</b-nav-item>
            <b-nav-item-dropdown v-if="getConfig['show_bookings_button']" :text="$t('components.navbar.bookings.text')">
              <b-dropdown-item @click="menuGoToBookingSummary()">{{ $t("components.navbar.bookings.summary") }}</b-dropdown-item>
              <b-dropdown-item v-if="getUser.role_id === 'admin'" @click="menuGoToPlanning()">{{ $t("components.navbar.bookings.planning") }}</b-dropdown-item>
            </b-nav-item-dropdown>
            <b-nav-item
              v-if="getConfig['show_admin_button']"
              @click="loginAdmin()"
            >
                {{ $t("components.navbar.admin") }}
            </b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items -->
          <b-navbar-nav class="ml-auto">
            <b-nav-item disabled><span class="text-white">{{ getUser.name }} [{{ getUser.role_id }}]</span></b-nav-item>

            <b-nav-item href="#" @click="logout()"
              ><b-icon
                icon="power"
                aria-hidden="true"
                class="text-white"
              ></b-icon
            ></b-nav-item>
          </b-navbar-nav>
        </b-collapse>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { mapActions, mapGetters } from 'vuex'
import Logo from '@/components/Logo.vue'

export default {
  components: {
    Logo
  },
  beforeMount: async function () {
    this.fetchConfig()
  },
  computed: {
    ...mapGetters([
      'getConfig',
      'getUser'
    ])
  },
  methods: {
    ...mapActions([
      'logout',
      'fetchVpn',
      'fetchConfig',
      'loginAdmin',
      'goToBookingSummary'
    ]),
    menuGoToBookingSummary () {
      this.goToBookingSummary()
    },
    menuGoToPlanning () {
      this.$store.dispatch('navigate', 'Planning')
    }
  }
}
</script>
