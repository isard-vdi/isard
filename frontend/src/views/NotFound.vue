<template>
  <b-container fluid class="vh-100">
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1"/>
      <b-col md="10">
        <h1>No hem pogut trobar l'adreça sol·licitada</h1>
        <b-button @click="redirectLogin()" class="btn mt-4" variant="primary" size="lg">
          <b-icon icon="house-door-fill" variant="white"></b-icon>
          Tornar a l'inici
        </b-button>
        </b-col>
        <b-col md="1"/>
      </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  methods: {
    redirectLogin: function () {
      this.$router.push({ path: '/' })
    }
  }
}

</script>
