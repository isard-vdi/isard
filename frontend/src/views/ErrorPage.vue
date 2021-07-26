<template>
    <b-container fluid class="vh-100">
        <b-row class="h-100 d-flex justify-content-center align-items-center">
            <b-col md="3" />
            <b-col md="6">
                <h1 class="mb-2">
                    <b-icon variant="danger" class="mr-2" icon="exclamation-circle-fill"></b-icon>
                    {{ $t('views.error.title') }}
                </h1>
                <h2>{{ error }}</h2>
                <b-button @click="navigate('Home')">{{ $t('views.error.go-home') }}</b-button>
            </b-col>
            <b-col md="3" />
        </b-row>
    </b-container>
</template>

<script>
import { mapActions } from 'vuex'

// @ is an alias to /src

export default {
  data () {
    const error = this.isNullOrUndefined(
      this.$t('views.error.codes')[this.$route.params.code && this.$route.params.code.toString()]
    )
      ? this.$t('views.error.codes')['500']
      : this.$t('views.error.codes')[this.$route.params.code && this.$route.params.code.toString()]
    return {
      error: error
    }
  },
  methods: {
    ...mapActions([
      'navigate'
    ])
  }
}
</script>
