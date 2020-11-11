<template>
  <b-container fluid>
    <b-row id="admin" align-h="end">
      <b-button :href="'/isard-admin/login/' + category.id" size="sm" variant="outline-secondary">Administració</b-button>
    </b-row>
    <b-row id="login" align-h="center">
      <b-col sm="10" md="6" lg="5" xl="4">
        <img id="logo" src="@/assets/logo.svg" alt="IsardVDI logo. It's a head of an Isard" />

        <h1>IsardVDI | Iniciar Sessió</h1>
        <h3 v-show="category.id !== 'default'">{{ category.name }}</h3>

        <b-form method="POST" :action="login('local')">
          <b-form-input id="username" name="usr" type="text" required placeholder="Nom d'usuari" />

          <b-form-input
            id="password"
            name="pwd"
            type="password"
            required
            placeholder="Contrasenya"
          />

          <b-button id="submit" type="submit" variant="warning" size="lg">Iniciar sessió</b-button>
        </b-form>

        <hr />

        <p>O iniciar sessió amb</p>

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

export default {
  name: 'login',
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
        this.$router.push({ name: 'NotFound' })
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
#admin a {
  margin-top: 25px;
  margin-right: 25px;
}

#logo {
  width: 125px;
  margin-top: 100px;
  margin-bottom: 50px;
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
