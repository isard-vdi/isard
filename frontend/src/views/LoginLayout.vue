<template>
  <b-container
    id="login"
    fluid
    class="h-100 w-100 pt-5 pt-md-0 scrollable-div"
  >
    <b-row
      class="h-100 justify-content-center ml-2 mr-2 mr-md-5"
      align-v="center"
    >
      <b-col
        cols="3"
        sm="3"
        md="6"
        lg="8"
        xl="8"
        class="d-flex justify-content-center"
      >
        <Logo style="max-width: 35rem; max-height: 25rem;" />
      </b-col>

      <b-col
        cols="12"
        sm="12"
        md="6"
        lg="4"
        xl="4"
        class="pb-5 mb-5 pb-md-0 mb-md-0 d-flex flex-column align-content-center"
      >
        <b-row class="mr-xl-5 pr-xl-3">
          <b-col class="d-flex flex-column">
            <!-- Spacer -->
            <b-row
              class="justify-content-center mb-md-3"
              style="height: 2rem"
            />
            <!-- Title -->
            <b-row class="d-flex flex-column justify-content-center mb-3">
              <h1>
                {{ title }}
              </h1>
            </b-row>
            <!-- Language selection -->
            <b-row>
              <Language
                class="ml-3 mt-2 mt-md-4 mb-3"
              />
            </b-row>

            <router-view />
            <!-- Powered By-->
            <b-row
              id="powered-by"
              align-h="center"
              class="mt-5"
            >
              <b-col class="text-center">
                <PoweredBy />
                <a
                  href="isard_changelog_link"
                  target="_blank"
                >
                  <p ref="version">isard_display_version</p>
                </a>
              </b-col>
            </b-row>
          </b-col>
        </b-row>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import Language from '@/components/Language.vue'
import Logo from '@/components/Logo.vue'
import PoweredBy from '@/components/shared/PoweredBy.vue'
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  name: 'LoginLayout',
  components: {
    Language,
    Logo,
    PoweredBy
  },
  setup (props, context) {
    const $store = context.root.$store
    const currentRoute = computed(() => $store.getters.getCurrentRoute)

    const title = computed(() => {
      if (currentRoute.value === 'Login') {
        return i18n.t('views.login.title')
      } else {
        return i18n.t('views.select-category.title')
      }
    })

    return {
      title
    }
  }
}
</script>

<style scoped>
  #login {
    text-align: center;
  }

  #powered-by {
    margin: 4rem;
  }
  #isard-logo {
    width: 3rem;
    margin: -3rem 0.5rem 0 0.5rem;
  }

  #login form {
    margin: 25px;
  }

  #login form input {
    margin-bottom: 18px;
  }

  .login-btn {
    margin: 10px;
  }

  .login-btn svg {
    margin-right: 10px;
  }

  /* background -> brand color; border -> background: darken(brand color, 5%); */
  .btn-github {
    color: #fff !important;
    background-color: #333 !important;
    border-color: #262626 !important;
  }

  .btn-google {
    color: #fff !important;
    background-color: #4285f4 !important;
    border-color: #2a75f3 !important;
  }

  #powered-by a {
    color: inherit !important;
    text-decoration: none !important;
  }
</style>
