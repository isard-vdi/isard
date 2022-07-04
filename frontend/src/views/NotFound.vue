<template>
  <b-container
    fluid
    class="vh-100"
  >
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1" />
      <b-col md="10">
        <h1>{{ $t('views.not-found.title') }}</h1>
        <b-button
          class="btn mt-4"
          variant="primary"
          size="lg"
          @click="redirectLogin()"
        >
          <b-icon
            icon="house-door-fill"
            variant="white"
          />
          {{ $t('views.not-found.back') }}
        </b-button>
      </b-col>
      <b-col md="1" />
    </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  setup (props, context) {
    const redirectLogin = () => {
      context.root.$router.push({ path: '/' })
    }
    return {
      redirectLogin
    }
  }
}

</script>
