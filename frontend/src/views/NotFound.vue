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
          src="@/assets/img/404.svg"
          alt=""
          style="max-height: 15rem; min-height: 10rem;"
          fluid-grow
        />
        <span class="text-left">
          <h1 class="mb-4">
            <b>Oops...</b><br>
            <b>{{ $t('views.not-found.title') }}</b>
          </h1>
          <p>
            {{ $t('views.not-found.subtitle') }}<br>
            {{ $t('views.not-found.home') }} <b
              class="cursor-pointer"
              @click="navigate('Login')"
            ><u>{{ $t('views.not-found.here') }}</u></b>
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

export default {
  methods: {
    ...mapActions([
      'navigate'
    ])
  }
}
</script>
