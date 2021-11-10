<template>
    <b-container fluid>
        <b-row id="header" align-h="center">
            <Logo/>
        </b-row>
        <b-row id="register" align-h="center">
            <b-col sm="10" md="6" lg="5" xl="4">
                <h1>{{ $t('views.register.title') }}</h1>
                <b-form @submit.prevent="register(code)">
                <b-alert
                  v-model="showAlert"
                  variant="danger"
                >
                {{ this.getPageErrorMessage }}
                </b-alert>
                <b-form-input
                    type="text"
                    v-model="code"
                    required
                    :placeholder="$t('views.register.code')"
                />
                  <b-button type="submit" variant="warning" size="lg">{{ $t('views.register.register') }}</b-button>
                  <b-button @click="deleteSessionAndGoToLogin()" class="ml-3" variant="primary" size="lg">{{ $t('views.cancel') }}</b-button>
                </b-form>
            </b-col>
        </b-row>
    </b-container>
</template>

<script>
import Logo from '@/components/Logo.vue'
import { mapActions, mapGetters } from 'vuex'

export default {
  name: 'register',
  components: {
    Logo
  },
  methods: {
    ...mapActions([
      'register',
      'deleteSessionAndGoToLogin'
    ])
  },
  computed: {
    ...mapGetters([
      'getPageErrorMessage'
    ]),
    showAlert () {
      return this.getPageErrorMessage !== ''
    }
  },
  data () {
    return {
      code: ''
    }
  }
}
</script>

<style scoped>
#header {
  padding: 25px 25px 0 25px;
  margin-bottom: 100px;
}

#register form {
    margin: 25px;
}

#register form input {
    margin-bottom: 18px;
}
</style>
