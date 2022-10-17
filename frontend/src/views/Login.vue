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
            <b-row class="justify-content-center mb-3">
              <h1 v-if="show_login_extras">
                {{ $t('views.login.title') }}
              </h1>
            </b-row>
            <!-- Category by path display -->
            <b-row
              v-if="category_by_path"
              class="ml-2 mt-2"
            >
              <h3>{{ category_name }}</h3>
            </b-row>
            <!-- Language selection -->
            <b-row>
              <Language
                v-if="show_login_extras"
                class="ml-3 mt-2 mt-md-4 mb-3"
              />
            </b-row>
            <!-- Login form -->
            <b-form
              v-if="show_login_form"
              class="m-0"
              @submit.prevent="login('form')"
            >
              <!-- Error message -->
              <b-alert
                v-model="showDismissibleAlert"
                dismissible
                variant="danger"
              >
                {{ getPageErrorMessage }}
              </b-alert>
              <!-- Category selection -->
              <v-select
                v-if="!category_by_path && getCategories.length > 1"
                ref="select_category"
                v-model="category"
                class="mb-3"
                size="md"
                required
                :options="categories_select"
                :reduce="category => category.value"
                :placeholder="$t('views.login.form.select-category')"
              >
                <template #search="{attributes, events}">
                  <input
                    class="vs__search"
                    style="margin-bottom: 0px"
                    :required="!category"
                    v-bind="attributes"
                    v-on="events"
                  >
                </template>
              </v-select>
              <b-form-input
                v-model="usr"
                type="text"
                required
                :placeholder="$t('views.login.form.usr')"
              />
              <b-form-input
                v-model="pwd"
                type="password"
                required
                :placeholder="$t('views.login.form.pwd')"
              />
              <b-button
                type="submit"
                size="lg"
                class="btn-green w-100 rounded-pill mt-2 mt-md-5"
              >
                {{ $t('views.login.form.login') }}
              </b-button>
            </b-form>
            <div v-if="show_login_providers">
              <hr
                class="m-4"
                style="border-bottom: 1px solid #ececec;"
              >
              <div class="d-flex flex-row flex-wrap justify-content-center align-items-center">
                <p class="w-100 text-center">
                  {{ $t('views.login.other-logins') }}
                </p>
                <b-button
                  v-for="provider in getProviders"
                  :key="provider"
                  :class="'rounded-pill mt-0 btn-sm login-btn btn-' + provider.toLowerCase()"
                  @click="login(provider.toLowerCase())"
                >
                  <font-awesome-icon
                    v-if="!['saml'].includes(provider)"
                    :icon="['fab', provider.toLowerCase()]"
                  />
                  {{ provider }}
                </b-button>
              </div>
            </div>
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
                <b-spinner v-if="loading" />
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
  name: 'Login',
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
      'getProviders',
      'getPageErrorMessage'
    ]),
    categories_select () {
      return this.getCategories.map(category =>
        ({
          value: category.id,
          label: category.name
        })
      )
    },
    category_by_path () {
      return this.$route.params.category !== undefined
    },
    category_name () {
      let name = ''
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
      return this.show_login_form && this.getProviders.length
    },
    show_login_extras () {
      return this.show_login_form || this.show_login_providers
    }
  },
  watch: {
    category: function () {
      if (!this.category_by_path) {
        localStorage.category = this.category
      }
    }
  },
  beforeMount: async function () {
    if (localStorage.token) {
      this.$router.push({ name: 'desktops' })
    }
    this.$store.dispatch('removeAuthorizationCookie')
    this.$store.dispatch('fetchProviders')
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

    if (this.$route.query.error) {
      this.$store.dispatch('parseErrorFromQuery', this.$route.query.error)
      this.showDismissibleAlert = true
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
          .dispatch('login', data, this.$refs.version)
          .then(() => {})
          .catch(err => {
            console.log(err)
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
