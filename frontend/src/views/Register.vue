<template>
    <b-container fluid>
        <b-row id="header" align-h="center">
            <Title />
        </b-row>
        <b-row id="register" align-h="center">
            <b-col sm="10" md="6" lg="5" xl="4">
                <h1>{{ $t('views.register.title') }}</h1>

                <b-form method="POST" :action="register()">
                    <b-form-input
                        id="code"
                        name="code"
                        type="text"
                        required
                        :placeholder="$t('views.register.code')"
                    />

                    <b-button id="submit" type="submit" variant="warning" size="lg">{{ $t('views.register.register') }}</b-button>
                </b-form>
            </b-col>
        </b-row>
    </b-container>
</template>

<script>
import Title from '@/components/Title.vue'
export default {
  name: 'register',
  components: {
    Title
  },
  methods: {
    register () {
      let redirect = new URLSearchParams(window.location.search).get(
        'redirect'
      )
      if (redirect !== '') {
        redirect = '?redirect=' + redirect
      }
      return (
                `${window.location.protocol}//${window.location.host}/api/v2/register` +
                redirect
      )
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
