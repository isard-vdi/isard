<template>
  <b-container
    fluid
    class="h-100 w-100 pt-5 pt-md-0 scrollable-div"
  >
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col
        cols="3"
      />
      <b-col
        cols="6"
        class="text-center"
      >
        <b-img
          :src="require(`@/assets/img/${$route.params.code}.svg`)"
          alt=""
          style="max-height: 15rem; min-height: 10rem;"
          fluid-grow
        />
        <span class="text-left">
          <h1 class="mb-4">
            <b>Oops...</b><br>
            <b>{{ $t(`views.error.codes.${$route.params.code}.title`) }}</b>
          </h1>
          <p>
            {{ $t(`views.error.codes.${$route.params.code}.subtitle`) }}<br>
            {{ $t(`views.error.codes.${$route.params.code}.home`) }} <b
              class="cursor-pointer"
              @click="navigate('Login')"
            ><u>{{ $t('views.error.here') }}</u></b>
          </p>
        </span>
      </b-col>
      <b-col
        cols="3"
      />
    </b-row>
  </b-container>
</template>
<script>
import { mapActions } from 'vuex'

// @ is an alias to /src
import { StringUtils } from '../utils/stringUtils'

export default {
  data () {
    const error = StringUtils.isNullOrUndefinedOrEmpty(
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
