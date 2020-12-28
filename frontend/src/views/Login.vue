<template>
  <b-container fluid>
    <b-row id="header">
      <b-col>
        <Language />
      </b-col>

      <b-col>
        <Logo/>
      </b-col>

      <b-col>
        <b-button v-if="configLoaded && config['show_admin_button']" :href="'/isard-admin/login/' + category" size="sm" variant="outline-secondary">{{ $t('views.login.admin') }}</b-button>
      </b-col>
    </b-row>
    <b-row id="login" align-h="center">
      <b-col sm="10" md="6" lg="5" xl="4">
        <h1 v-if="categories.length || config['social_logins']">{{ $t('views.login.title') }}</h1>
        <h3 v-if="category_by_path">{{ category_name }}</h3>

        <b-form v-if="categories.length" @submit.prevent="login('local')">

          <b-alert
            v-model="showDismissibleAlert"
            dismissible
            variant="danger"
          >
            {{ this.error }}
          </b-alert>

          <b-form-select
            v-if="!category_by_path && categories.length > 1"
            size="md"
            class="mb-4"
            required
            :options="categories_select"
            v-model="category"
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

        <hr v-if="categories.length && config['social_logins']"/>

        <p v-if="categories.length && config['social_logins']">{{ $t('views.login.other-logins') }}</p>

        <b-button
          v-for="provider in config['social_logins']"
          v-bind:key="provider"
          @click="login(provider.toLowerCase())"
          :class="'login-btn btn-' + provider.toLowerCase()"
        >
          <font-awesome-icon :icon="['fab', provider.toLowerCase()]" />
          {{ provider }}
        </b-button>
        <hr v-if="categories.length || config['social_logins']"/>
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
      categories_select: [],
      category: '',
      usr: '',
      pwd: '',
      window: window,
      error: '',
      showDismissibleAlert: false
    }
  },
  computed: {
    categories () {
      return this.$store.state.categories
    },
    config () {
      return this.$store.getters.getConfig
    },
    configLoaded () {
      return this.$store.getters.getConfigLoaded
    },
    category_by_path () {
      return this.$route.params.category !== undefined
    },
    category_name () {
      var name = ''
      this.categories.forEach(category => {
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
        const data = new FormData()
        data.append('category', this.category)
        data.append('provider', provider)
        data.append('usr', this.usr)
        data.append('pwd', this.pwd)
        this.$store
          .dispatch('login', data)
          .then(() => { this.$router.push({ name: 'SelectTemplate' }) })
          .catch(err => {
            this.error = this.$t('views.error.codes')[err.response.status.toString()]
            this.showDismissibleAlert = true
          })
      } else {
        window.location = `${window.location.protocol}//${window.location.host}/api/v2/login/${this.category}?provider=${provider}&redirect=/select_template`
      }
    }
  },
  beforeMount: async function () {
    this.$store.dispatch('fetchConfig')

    this.$store.dispatch('fetchCategories').then(() => {
      if (this.categories.length === 1) {
        this.category = this.categories[0].id
      } else {
        this.categories_select = this.categories.map(category =>
          ({
            value: category.id,
            text: category.name
          })
        )
      }
    }).catch(err => {
      if (err.response.status === 404) {
        // this.$router.push({ name: 'NotFound' })
      } else {
        this.$router.push({
          name: 'Error',
          params: { code: err.response.status.toString() }
        })
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
#header {
  padding: 25px 25px 0 25px;
  margin-bottom: 50px;
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

a {
  color: inherit !important;
  text-decoration: none !important;
}

</style>
