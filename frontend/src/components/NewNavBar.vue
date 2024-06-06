<template>
  <div
    id="navbar"
    class="bg-darkgray px-0 px-lg-5 pl-4"
  >
    <b-container
      fluid
      class="px-0"
    >
      <b-navbar
        toggleable="lg"
        type="dark"
        variant=""
      >
        <div id="logo-wrapper">
          <Logo />
        </div>
        <b-navbar-toggle
          class="ml-auto"
          target="nav-collapse"
        />

        <b-collapse
          id="nav-collapse"
          is-nav
        >
          <b-navbar-nav
            id="left-side"
            class="mt-5 mt-lg-0"
          >
            <b-nav-item
              :to="{ name: 'desktops' }"
              active-class="active"
            >
              <font-awesome-icon
                :icon="['fas', 'desktop']"
                class="mr-1 d-lg-none d-xl-inline"
              />
              {{ $t("components.navbar.desktops") }}
            </b-nav-item>
            <b-nav-item
              v-if="getUser.role_id !== 'user'"
              :to="{ name: 'templates' }"
              active-class="active"
            >
              <font-awesome-icon
                :icon="['fas', 'cubes']"
                class="mr-1 d-lg-none d-xl-inline"
              />
              {{ $t("components.navbar.templates") }}
            </b-nav-item>
            <b-nav-item
              v-if="getUser.role_id !== 'user'"
              :to="{ name: 'media' }"
              active-class="active"
            >
              <font-awesome-icon
                :icon="['fas', 'compact-disc']"
                class="mr-1 d-lg-none d-xl-inline"
              />
              {{ $t("components.navbar.media") }}
            </b-nav-item>
            <b-nav-item
              v-if="getUser.role_id !== 'user'"
              :to="{ name: 'deployments' }"
              active-class="active"
            >
              <b-iconstack
                class="pt-1 d-lg-none d-xl-inline"
              >
                <b-icon
                  stacked
                  icon="tv"
                  shift-v="4"
                  shift-h="-4"
                />
                <b-icon
                  stacked
                  icon="tv-fill"
                />
              </b-iconstack>
              {{ $t("components.navbar.deployments") }}
            </b-nav-item>
            <b-nav-item
              v-if="getConfig.showBookingsButton && getUser.role_id !== 'admin'"
              active-class="active"
              @click="menuGoToBookingSummary()"
            >
              <font-awesome-icon
                :icon="['fas', 'calendar']"
                class="mr-1 d-lg-none d-xl-inline"
              />
              {{ $t('components.navbar.bookings.text') }}
            </b-nav-item>
            <b-nav-item-dropdown
              v-if="getConfig.showBookingsButton && getUser.role_id === 'admin'"
              active-class="active"
            >
              <template #button-content>
                <font-awesome-icon
                  :icon="['fas', 'calendar']"
                  class="mr-1 d-lg-none d-xl-inline"
                />
                {{ $t('components.navbar.bookings.text') }}
              </template>
              <b-dropdown-item @click="menuGoToBookingSummary()">
                {{ $t("components.navbar.bookings.summary") }}
              </b-dropdown-item>
              <b-dropdown-item
                @click="menuGoToPlanning()"
              >
                {{ $t("components.navbar.bookings.planning") }}
              </b-dropdown-item>
            </b-nav-item-dropdown>
            <b-nav-item
              :to="{ name: 'userstorage' }"
              active-class="active"
            >
              <b-icon
                icon="folder-fill"
              />
              {{ $t("components.navbar.storage") }}
            </b-nav-item>
            <b-nav-item
              v-if="['admin', 'manager'].includes(getUser.role_id)"
              href="/isard-admin/admin/landing"
            >
              <font-awesome-icon
                :icon="['fas', 'user-cog']"
                class="mr-1 d-lg-none d-xl-inline"
              />
              {{ $t("components.navbar.admin") }}
            </b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items -->
          <b-navbar-nav class="ml-auto">
            <b-nav-item-dropdown right>
              <!-- Using 'button-content' slot -->
              <template #button-content>
                <b-avatar
                  class="mr-2"
                  size="1.5rem"
                />
                <span>{{ getUser.name }} [{{ getUser.role_name }}]</span>
              </template>
              <b-dropdown-item
                href="#"
                @click="navigate('profile')"
              >
                <b-icon
                  icon="person-fill"
                  class="mr-2 d-lg-none d-xl-inline"
                  scale="0.75"
                />
                {{ $t("components.navbar.profile") }}
              </b-dropdown-item>
              <b-dropdown-item
                :href="getConfig.documentationUrl"
                target="_blank"
              >
                <b-icon
                  icon="journal-text"
                  class="mr-2 d-lg-none d-xl-inline"
                  scale="0.75"
                />
                {{ $t("components.navbar.help") }}
              </b-dropdown-item>
              <b-dropdown-item
                :href="goToViewersGuide()"
                target="_blank"
              >
                <b-icon
                  icon="info-circle"
                  class="mr-2 d-lg-none d-xl-inline"
                  scale="0.75"
                />
                {{ $t("components.navbar.viewers") }}
              </b-dropdown-item>
              <b-dropdown-item
                href="#"
                @click="fetchVpn()"
              >
                <b-icon
                  icon="download"
                  class="mr-2 d-lg-none d-xl-inline"
                  scale="0.75"
                />
                {{ $t("components.navbar.vpn.download") }}
              </b-dropdown-item>
              <b-dropdown-item
                href="#"
                @click="logout(true)"
              >
                <b-icon
                  icon="box-arrow-in-right"
                  class="mr-2 d-lg-none d-xl-inline"
                  scale="0.75"
                />
                {{ $t("components.navbar.logout") }}
              </b-dropdown-item>
            </b-nav-item-dropdown>
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
      'navigate'
    ]),
    menuGoToBookingSummary () {
      this.$store.dispatch('navigate', 'bookingsummary')
    },
    menuGoToPlanning () {
      this.$store.dispatch('navigate', 'Planning')
    },
    goToViewersGuide () {
      if (localStorage.language === 'es') {
        return 'https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers.es/'
      } else if (localStorage.language === 'ca') {
        return 'https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers.ca/'
      } else {
        return 'https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/'
      }
    }
  }
}
</script>
