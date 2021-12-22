<template>
    <b-container fluid class="justify-content-center pt-lg-5 min-vh-100">
      <!-- logo -->
      <b-row class="mt-5">
        <b-col cols="1" lg="4"></b-col>
        <b-col cols="10" lg="4" class="justify-content-center d-flex right-separator-border rounded-top-30" style="height: 8rem;">
          <div id="logo-wrapper">
            <Logo/>
          </div>
        </b-col>
        <b-col cols="1" lg="4"></b-col>
      </b-row>
      <!-- Title -->
      <b-row align-h="center" class="justify-content-center pt-1 pb-1">
        <h1>{{ $t('views.register.title') }}</h1>
      </b-row>
      <!-- Form -->
      <b-row align-h="center" class="justify-content-center pt-1 pb-1">
        <b-col cols="8" md="6" lg="4" xl="2">
          <b-form @submit.prevent="submitForm">
            <b-row align-h="center" class="justify-content-center">
              <b-alert
                v-model="showAlert"
                variant="danger"
              >
              {{ this.getPageErrorMessage }}
              </b-alert>
            </b-row>
            <b-row align-h="center" class="justify-content-center">
              <b-form-input
                  type="text"
                  class="py-4 mt-3 mb-3"
                  v-model="code"
                  :placeholder="$t('views.register.code')"
              />
              <div class="isard-form-error" v-if="v$.code.$error">{{ $t(`validations.${v$.code.$errors[0].$validator}`, { property: `${$t("forms.registration.code")}` }) }}</div>
            </b-row>
            <b-row align-h="center" class="justify-content-center mt-2 mb-3">
              <b-button type="submit" class="rounded-pill w-100 btn-green">{{ $t('views.register.register') }}</b-button>
            </b-row>
            <b-row align-h="center" class="justify-content-center mt-3">
              <b-button @click="deleteSessionAndGoToLogin()" class="rounded-pill w-100 btn-red">{{ $t('views.cancel') }}</b-button>
            </b-row>
          </b-form>
        </b-col>
      </b-row>
      <!-- Footer -->
      <b-row id="powered-by" align-h="center">
        <PoweredBy/>
      </b-row>
    </b-container>
</template>

<script>
import PoweredBy from '@/components/shared/PoweredBy.vue'
import Logo from '@/components/Logo.vue'
import { mapActions, mapGetters } from 'vuex'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'

export default {
  setup (props, context) {
    return {
      v$: useVuelidate()
    }
  },
  name: 'register',
  components: {
    Logo,
    PoweredBy
  },
  validations () {
    return {
      code: {
        required
      }
    }
  },
  methods: {
    ...mapActions([
      'register',
      'deleteSessionAndGoToLogin'
    ]),
    async submitForm () {
      const isFormCorrect = await this.v$.$validate()

      if (isFormCorrect) {
        this.register(this.code)
      }
    }
  },
  computed: {
    ...mapGetters([
      'getPageErrorMessage'
    ]),
    showAlert () {
      return this.getPageErrorMessage !== ''
    }
  },
  data () {
    return {
      code: ''
    }
  }
}
</script>
