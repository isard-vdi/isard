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
        <b-button href="/isard-admin" size="sm" variant="outline-secondary">{{ $t('views.login.admin') }}</b-button>
      </b-col>
    </b-row>
    <b-row id="login" align-h="center">
      <b-col sm="10" md="6" lg="5" xl="4">
        <h1>{{ $t('views.login.title') }}</h1>
        <h3 v-show="category.id !== 'default'">{{ category.name }}</h3>

        <b-form method="POST" :action="login('local')">
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
      category: {
        id: '',
        name: '',
        icon: ''
      },
      window: window,
      socialLogin: ['GitHub', 'Google']
    }
  },
  methods: {
    login (provider) {
      return `${window.location.protocol}//${window.location.host}/api/v2/login/${this.category.id}?provider=${provider}&redirect=/select_template`
    }
  },
  beforeMount: async function () {
    this.category.id = this.$route.params.category
    if (this.category.id === undefined) {
      this.category.id = 'default'
    }

    try {
      const rsp = await apiAxios.get('/category/' + this.category.id)
      this.category.name = rsp.data.name
    } catch (err) {
      console.error(err)
      if (err.response.status === 404) {
        // this.$router.push({ name: 'NotFound' })
      } else {
        this.$router.push({
          name: 'Error',
          params: { code: err.response.status.toString() }
        })
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
