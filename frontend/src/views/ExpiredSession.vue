<template>
    <b-container fluid class="vh-100">
        <b-row class="h-100 d-flex justify-content-center align-items-center">
            <b-col md="1" />
            <b-col md="10">
                <b-iconstack font-scale="5" variant="dark">
                    <b-icon stacked icon="clock-history" font-scale="2" shift-h="-7.5" shift-v="7"></b-icon>
                    <b-icon stacked icon="exclamation-triangle-fill" variant="warning"></b-icon>
                </b-iconstack>
                <h1 class="mt-2">{{ $t('views.expired-session.title') }}</h1>
                <h2>{{ $t('views.expired-session.subtitle') }}</h2>
                <b-button class="btn mt-2" variant="primary" size="lg" @click="redirectLogin()">
                    <b-icon icon="unlock-fill" variant="white"></b-icon>
                    {{ $t('views.expired-session.button') }}
                </b-button>
            </b-col>
            <b-col md="1" />
        </b-row>
    </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  methods: {
    redirectLogin: function () {
      this.$router.push({ name: 'Login' })
    }
  }
}
</script>
