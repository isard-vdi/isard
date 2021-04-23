<template>
  <diV>
    <b-navbar toggleable="lg" type="light" variant="light">
      <b-navbar-brand>
        <b-img
          id="logo"
          src="/custom/logo.svg"
          :alt="$t('components.title.logo-alt')"
        />
      </b-navbar-brand>
      <b-navbar-toggle target="nav-collapse"></b-navbar-toggle>
      <b-collapse id="nav-collapse" is-nav>
        <b-navbar-nav>
          <b-nav-item v-b-modal.help_modal>
            <b-icon icon="question-circle-fill" scale="1.5" class="mr-2"></b-icon>
            {{ $t("components.navbar.help") }}
          </b-nav-item>
          <b-nav-item @click="fetchVpn()">
            <b-icon icon="shield-lock" scale="1.5" class="mr-2"></b-icon>
            {{ $t("components.navbar.vpn.download") }}
          </b-nav-item>
          <b-nav-item
            v-if="config['show_admin_button']"
            href="/isard-admin/login"
          >
            <b-icon icon="gear" scale="1.5" class="mr-2"></b-icon>
            {{ $t("components.navbar.admin") }}
          </b-nav-item>
        </b-navbar-nav>
        <b-navbar-nav class="ml-auto">
          <b-nav-item right>
            <b-avatar class="mr-3" v-if="user.photo" :src="user.photo" :size="35"></b-avatar>
            <b-avatar class="mr-3" :size="35" v-else></b-avatar>
            <span class="mr-auto">{{ user.name }} [{{ user.role }}]</span>
          </b-nav-item>
          <b-nav-item href="#" @click="logout()" class="mt-1" right>
            <b-icon variant="danger" icon="power" scale="1"></b-icon>
          </b-nav-item>
        </b-navbar-nav>
      </b-collapse>
    </b-navbar>
    <Help />
  </diV>
</template>
<script>
import Help from '@/components/Help.vue'
import { mapActions } from 'vuex'

export default {
  components: {
    Help
  },
  beforeMount: async function () {
    this.$store.dispatch('fetchConfig')
  },
  computed: {
    config () {
      return this.$store.getters.getConfig
    },
    user () {
      return this.$store.getters.getUser
    }
  },
  methods: {
    ...mapActions(['logout', 'fetchVpn'])
  }
}
</script>
<style scoped>
#logo {
  margin-top: 0cm;
  max-width: 35px;
  /* -webkit-filter: invert(1);
  filter: invert(1); */
}
</style>
