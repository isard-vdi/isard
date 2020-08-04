<template>
    <div>
        <p class="display-3">{{ $t('components.not-found.title') }}</p>
        <b-button @click="redirectLogin()" class="btn mt-4" variant="primary" size="lg">
            <b-icon icon="house-door-fill" variant="white"></b-icon>
            {{ $('components.not-found.home') }}
        </b-button>
    </div>
</template>

<script>
// @ is an alias to /src

export default {
  methods: {
    redirectLogin: function () {
      this.$router.push({ name: 'Welcome' })
    }
  }
}
</script>
