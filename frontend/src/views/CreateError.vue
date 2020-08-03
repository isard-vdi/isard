<template>
    <b-container fluid class="vh-100">
        <b-row class="h-100 d-flex justify-content-center align-items-center">
            <b-col md="1" />
            <b-col md="10">
                <b-iconstack font-scale="6" shift-v="4">
                    <b-icon
                        stacked
                        icon="x-octagon-fill"
                        variant="danger"
                        shift-v="1.75"
                        scale="0.75"
                    ></b-icon>
                    <b-icon stacked icon="tv" variant="dark" scale="2"></b-icon>
                </b-iconstack>
                <h1 class="mt-2">Error</h1>
                <h3>{{ $t('views.create-error.title') }}</h3>
                <b-button @click="redirectCreating()" class="btn mt-4" variant="primary" size="lg">
                    <b-icon icon="arrow-clockwise" variant="white"></b-icon>
                    {{ $t('views.create-error.retry') }}
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
    redirectCreating: function () {
      this.$router.push({ name: 'Creating' })
    }
  }
}
</script>
