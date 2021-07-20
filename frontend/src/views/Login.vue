<template>
  <b-container fluid id="login">
    <b-row id="header" class="mb-4">
      <b-col>
        <Logo/>
      </b-col>
    </b-row>
    <b-row>
      <b-col>
        <Language class="mb-4"/>
      </b-col>
    </b-row>
    <b-row id="login" align-h="center">
      <b-spinner v-if="loading" />
      <b-col v-else sm="10" md="6" lg="5" xl="4">
        <h1 v-if="getCategories.length || getConfig['social_logins']">{{ $t('views.login.title') }}</h1>
        <h3 v-if="category_by_path">{{ category_name }}</h3>

        <b-form v-if="getCategories.length" @submit.prevent="login('local')">

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
            required
            :options="categories_select"
            v-model="category"
            ref="select_category"
          >
            <template #first>
              <b-form-select-option value="" disabled>{{ $t('views.login.form.select-category') }}</b-form-select-option>
            </template>
          </b-form-select>

          <b-form-input v-model="usr" type="text" required :placeholder="$t('views.login.form.usr')" />

          <b-form-input
            type="password"
            required
            v-model="pwd"
            :placeholder="$t('views.login.form.pwd')"
          />

          <b-button type="submit" variant="warning" size="lg">{{ $t('views.login.form.login') }}</b-button>
        </b-form>

        <hr v-if="getCategories.length && getConfig['social_logins']"/>

        <p v-if="getCategories.length && getConfig['social_logins']">{{ $t('views.login.other-logins') }}</p>

        <b-button
          v-for="provider in getConfig['social_logins']"
          v-bind:key="provider"
          @click="login(provider.toLowerCase())"
          :class="'login-btn btn-' + provider.toLowerCase()"
        >
          <font-awesome-icon :icon="['fab', provider.toLowerCase()]" />
          {{ provider }}
        </b-button>
        <hr v-if="getCategories.length || getConfig['social_logins']"/>
      </b-col>
    </b-row>
    <b-row id="powered-by" align-h="center">
      <b-col>
        <a href="https://isardvdi.com/" target="_blank">
          {{ $t('views.login.powered-by') }}
          <img id="isard-logo" src="@/assets/logo.svg" :alt="$t('views.login.isard-logo-alt')" />
          <strong>IsardVDI</strong>
        </a>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import * as cookies from 'tiny-cookie'
import { mapGetters } from 'vuex'
import Language from '@/components/Language.vue'
import Logo from '@/components/Logo.vue'

export default {
  name: 'login',
  components: {
    Language,
    Logo
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
      return name
    }
  },
  methods: {
    login (provider) {
      if (provider === 'local') {
        this.loading = true
        const data = new FormData()
        data.append('category', this.category)
        data.append('provider', provider)
        data.append('usr', this.usr)
        data.append('pwd', this.pwd)
        this.$store
          .dispatch('login', data)
          .then(() => { this.$router.push({ name: 'Home' }) })
          .catch(err => {
            this.error = this.$t('views.error.codes')[err.response && err.response.status.toString()]
            this.showDismissibleAlert = true
            this.loading = false
          })
      } else {
        if (this.category) {
          window.location = `${window.location.protocol}//${window.location.host}/api/v2/login/${this.category}?provider=${provider}&redirect=/`
        } else {
          this.$refs.select_category.$el.reportValidity()
        }
      }
    }
  },
  beforeMount: async function () {
    this.$store.dispatch('fetchConfig')
    this.$store.dispatch('fetchCategories').then(() => {
      if (this.getCategories.length === 1) {
        this.category = this.getCategories[0].id
      }
    })

    if (this.category_by_path) {
      this.category = this.$route.params.category
    } else {
      this.category = cookies.getCookie('category') || ''
    }
  },
  watch: {
    category: function () {
      if (!this.category_by_path) {
        cookies.setCookie('category', this.category)
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
