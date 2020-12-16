<template>
  <b-container fluid class="vh-100">
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1"/>
      <b-col md="10">
        <h2 class="mt-4">
          <b-link v-b-modal.help_modal>{{ $t('views.landing.title.view-guide') }}</b-link>
        </h2>
        <Help/>
        <b-row>
          <b-col class="mt-4" xl="6" @click="openDesktop('remote')">
            <div class="big_button mr-1 ml-1">
              <b-iconstack font-scale="5" shift-v="4">
                <b-icon stacked icon="check" variant="success" shift-v="1"></b-icon>
                <b-icon stacked icon="tv" variant="dark" scale="2"></b-icon>
              </b-iconstack>
              <h2 class="mt-3">{{ $t('views.landing.buttons.local.title') }}</h2>
              <h4>
                <b-icon icon="star-fill" variant="warning"></b-icon>
                {{ $t('views.landing.buttons.local.description') }}
              </h4>
            </div>
          </b-col>
          <b-col class="mt-4" xl="6" @click="openDesktop('html')">
            <div class="big_button mr-1 ml-1">
              <b-iconstack font-scale="5" shift-v="4">
                <b-icon stacked icon="check" variant="success" shift-v="-3"></b-icon>
                <b-icon stacked icon="window" variant="dark" scale="2"></b-icon>
              </b-iconstack>
              <h2 class="mt-4">{{ $t('views.landing.buttons.browser.title') }}</h2>
              <h4>{{ $t('views.landing.buttons.browser.description') }}</h4>
            </div>
          </b-col>
        </b-row>
        <b-row class="mb-4 mt-4 mr-1 ml-1">
          <b-col cols="12" class="big_button" @click="destroyDesktop()">
            <b-iconstack font-scale="4" shift-v="6">
              <b-icon stacked icon="power" variant="danger" scale="2"></b-icon>
            </b-iconstack>
            <h2 class="mt-2">{{ $t('views.landing.buttons.logout.title') }}</h2>
            <h4>{{ $t('views.landing.buttons.logout.title') }}</h4>
          </b-col>
        </b-row>
      </b-col>
      <b-col md="1"/>
    </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src
import Help from '@/components/Help'
import { mapActions } from 'vuex'

export default {
  components: {
    Help
  },
  methods: {
    ...mapActions([
      'openDesktop',
      'destroyDesktop'
    ])
  }
}
</script>

<style scoped>
  .big_button {
    background-color:white;
    border: 5px solid #e9ecef;
    border-radius: 2rem;
    min-height:325px !important;
    padding-top: 75px;
  }

  .big_button:hover {
    background-color: #e9ecef;
    cursor: pointer;
  }
</style>
