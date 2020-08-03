<template>
    <b-container fluid class="vh-100">
        <b-row class="h-100 d-flex justify-content-center align-items-center">
            <b-col md="1" />
            <b-col md="10">
                <b-iconstack font-scale="6" shift-v="4">
                    <b-icon
                        stacked
                        icon="three-dots"
                        animation="cylon"
                        variant="primary"
                        shift-v="1.5"
                    ></b-icon>
                    <b-icon stacked icon="tv" variant="dark" scale="2"></b-icon>
                </b-iconstack>
                <h1 class="mt-4">{{ $t('views.creating.title') }}</h1>
                <h3>({{ $t('views.creating.subtitle') }})</h3>
            </b-col>
            <b-col md="1" />
        </b-row>
    </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  created () {
    const data = new FormData()
    data.append('template', this.$route.params.template)

    this.$store
      .dispatch('createDesktop', data)
      .then(() => this.$router.push({ name: 'Landing' }))
      .catch(e => {
        this.$router.push({ name: 'CreateError' })
      })
  }
}
</script>
