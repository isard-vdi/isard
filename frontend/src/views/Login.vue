<template>
  <b-container fluid>
    <b-row id="header">
      <b-col>
        <Language />
      </b-col>

      <b-col>
        <Title />
      </b-col>

      <b-col>
        <b-button v-if="configLoaded && config['show_admin_button']" :href="'/isard-admin/login/' + category" size="sm" variant="outline-secondary">{{ $t('views.login.admin') }}</b-button>
      </b-col>
    </b-row>
    <b-row id="login" align-h="center">
      <b-col sm="10" md="6" lg="5" xl="4">
        <h1>{{ $t('views.login.title') }}</h1>
        <h3 v-if="category_by_path">{{ category_name }}</h3>

        <b-form method="POST" :action="login('local')">
          <b-form-select v-if="!category_by_path" size="md" class="mb-4" required :options="categories" v-model="category">
            <template #first>
              <b-form-select-option value="" disabled>{{ $t('views.login.form.select-category') }}</b-form-select-option>
            </template>
          </b-form-select>

          <b-form-input id="username" name="usr" type="text" required :placeholder="$t('views.login.form.usr')" />

          <b-form-input
            id="password"
            name="pwd"
            type="password"
            required
            :placeholder="$t('views.login.form.pwd')"
          />

          <b-button id="submit" type="submit" variant="warning" size="lg">{{ $t('views.login.form.login') }}</b-button>
        </b-form>

        <hr />

        <p>{{ $t('views.login.other-logins') }}</p>

        <b-button
          v-for="provider in socialLogin"
          v-bind:key="provider"
          @click="window.location = login(provider.toLowerCase())"
          :class="'login-btn btn-' + provider.toLowerCase()"
        >
          <font-awesome-icon :icon="['fab', provider.toLowerCase()]" />
          {{ provider }}
        </b-button>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import { apiAxios } from '@/router/auth'
import * as cookies from 'tiny-cookie'
import Language from '@/components/Language.vue'
import Title from '@/components/Title.vue'

export default {
  name: 'login',
  components: {
    Language,
    Title
  },
  data () {
    return {
      categories: [],
      category: '',
      window: window,
      socialLogin: ['GitHub', 'Google']
    }
  },
  computed: {
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
        if (this.category === category.value) {
          name = category.text
        }
      })
      return name
    }
  },
  methods: {
    login (provider) {
      return `${window.location.protocol}//${window.location.host}/api/v2/login/${this.category}?provider=${provider}&redirect=/select_template`
    }
  },
  beforeMount: async function () {
    this.$store.dispatch('fetchConfig')

    await apiAxios.get('/categories').then(rsp => {
      this.categories = rsp.data.map(category =>
        ({
          value: category.id,
          text: category.name
        })
      )
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
  margin-bottom: 100px;
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
</style>
