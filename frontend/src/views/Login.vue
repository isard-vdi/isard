<template>
  <b-container fluid id="login" style="height: 100vh;">
    <b-row class="h-100">
      <b-col sm="12" md="6" lg="6" xl="8" class="justify-content-center align-content-center h-100 d-flex right-separator-border">
          <Logo style="margin-top: 20px;max-width: 250px;"/>
      </b-col>

      <b-col sm="12" md="6" lg="6" xl="4" class="d-flex flex-column justify-content-center align-content-start">
        <b-row id="login" class="justify-content-left">
          <b-spinner v-if="loading" />
          <b-col v-else sm="12" md="10" lg="9" xl="9" class="d-flex flex-column justify-content-start text-left">
            <h1 v-if="show_login_extras">{{ $t('views.login.title') }}</h1>
            <h3 v-if="category_by_path">{{ category_name }}</h3>
            <Language
              v-if="show_login_extras"
              class="d-inline-block mt-5 mb-4"
            />
            <b-form
              v-if="show_login_form"
              @submit.prevent="login('form')"
              class="m-0"
            >

              <b-alert
                v-model="showDismissibleAlert"
                dismissible
                variant="danger"
              >
                {{ this.error }}
              </b-alert>

              <b-form-select
                v-if="!category_by_path && getCategories.length > 1"
                size="md"
                class="mb-4"
                style="height:52px;"
                required
                :options="categories_select"
                v-model="category"
                ref="select_category"
              >
                <template #first>
                  <b-form-select-option value="" disabled>{{ $t('views.login.form.select-category') }}</b-form-select-option>
                </template>
              </b-form-select>

              <b-form-input v-model="usr" type="text" class="mb-4 py-4" required :placeholder="$t('views.login.form.usr')" />

              <b-form-input
                type="password"
                required
                v-model="pwd"
                class="py-4"
                :placeholder="$t('views.login.form.pwd')"
              />

              <b-button type="submit" size="lg" class="btn-green w-100 rounded-pill mt-4">{{ $t('views.login.form.login') }}</b-button>
            </b-form>

            <div v-if="show_login_providers">

              <hr class="m-4" style="border-bottom: 1px solid #ececec;"/>

              <div class="d-flex flex-row flex-wrap justify-content-center align-items-center">
                <p class="mb-3 w-100 text-center">{{ $t('views.login.other-logins') }}</p>
                <b-button
                  v-for="provider in getConfig['providers']"
                  v-bind:key="provider"
                  @click="login(provider.toLowerCase())"
                  :class="'rounded-pill btn-sm login-btn btn-' + provider.toLowerCase()"
                >
                  <font-awesome-icon :icon="['fab', provider.toLowerCase()]" />
                  {{ provider }}
                </b-button>
              </div>

            </div>
            <!-- Powered By-->
            <b-row id="powered-by" align-h="center">
              <b-col class="text-center">
                <PoweredBy/>
                <a href="isard_changelog_link" target="_blank">
                  <p>isard_display_version</p>
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
import { mapGetters } from 'vuex'
import Language from '@/components/Language.vue'
import Logo from '@/components/Logo.vue'
import { authenticationSegment } from '@/shared/constants'
import PoweredBy from '@/components/shared/PoweredBy.vue'

export default {
  name: 'login',
  components: {
    Language,
    Logo,
    PoweredBy
  },
  data () {
    return {
      loading: false,
      usr: '',
      pwd: '',
      window: window,
      error: '',
      showDismissibleAlert: false,
      category: ''
    }
  },
  computed: {
    ...mapGetters([
      'getCategories',
      'getConfig'
    ]),
    categories_select () {
      return this.getCategories.map(category =>
        ({
          value: category.id,
          text: category.name
        })
      )
    },
    category_by_path () {
      return this.$route.params.category !== undefined
    },
    category_name () {
      var name = ''
      this.getCategories.forEach(category => {
        if (this.category === category.id) {
          name = category.name
        }
      })
      if (!name) {
        name = this.category
      }
      return name
    },
    show_login_form () {
      return this.getCategories.length || this.category_by_path
    },
    show_login_providers () {
      return this.show_login_form && this.getConfig.providers.length
    },
    show_login_extras () {
      return this.show_login_form || this.show_login_providers
    }
  },
  methods: {
    login (provider) {
      if (provider === 'form') {
        this.loading = true
        const data = new FormData()
        data.append('category_id', this.category)
        data.append('provider', provider)
        data.append('username', this.usr)
        data.append('password', this.pwd)
        this.$store
          .dispatch('login', data)
          .then(() => {})
          .catch(err => {
            this.error = this.$t('views.login.errors')[err.response && err.response.status.toString()]
            this.showDismissibleAlert = true
            this.loading = false
          })
      } else {
        if (this.category) {
          window.location = `${window.location.protocol}//${window.location.host}${authenticationSegment}/login?provider=${provider}&category_id=${this.category}&redirect=/`
        } else {
          this.$refs.select_category.$el.reportValidity()
        }
      }
    }
  },
  beforeMount: async function () {
    if (localStorage.token) {
      this.$router.push({ name: 'desktops' })
    }
    this.$store.dispatch('removeAuthorizationCookie')
    this.$store.dispatch('fetchConfig')
    this.$store.dispatch('fetchCategories').then(() => {
      let defaultCategory = ''
      if (this.getCategories.length === 1) {
        defaultCategory = this.getCategories[0].id
      }
      if (this.category_by_path) {
        this.category = this.$route.params.category
      } else {
        if (this.getCategories.map(i => i.id).includes(localStorage.category)) {
          this.category = localStorage.category
        } else {
          this.category = defaultCategory
        }
      }
    })
  },
  watch: {
    category: function () {
      if (!this.category_by_path) {
        localStorage.category = this.category
      }
    }
  }
}
</script>

<style>
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
