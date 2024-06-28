<template>
  <b-container
    fluid
    class="justify-content-center pt-lg-5 min-vh-100"
  >
    <!-- logo -->
    <b-row class="mt-5">
      <b-col
        cols="1"
        lg="4"
      />
      <b-col
        cols="10"
        lg="4"
        class="
          justify-content-center
          d-flex
          right-separator-border
          rounded-top-30
        "
        style="height: 8rem"
      >
        <div id="logo-wrapper">
          <Logo />
        </div>
      </b-col>
      <b-col
        cols="1"
        lg="4"
      />
    </b-row>
    <!-- Title -->
    <b-row
      align-h="center"
      class="justify-content-center pt-1 pb-1"
    >
      <h1>{{ $t("views.register.title") }}</h1>
    </b-row>
    <!-- Form -->
    <b-row
      align-h="center"
      class="justify-content-center pt-1 pb-1"
    >
      <b-col
        cols="8"
        md="6"
        lg="4"
        xl="2"
      >
        <b-form @submit.prevent="submitForm">
          <b-row
            align-h="center"
            class="justify-content-center"
          >
            <b-alert
              v-model="showDismissibleAlert"
              variant="danger"
            >
              {{ $t(errorMessage.message, errorMessage.args) }}
            </b-alert>
          </b-row>
          <b-overlay
            :show="loading"
            rounded
            opacity="0"
            spinner-small
            spinner-variant="success"
          >
            <b-row
              align-h="center"
              class="justify-content-center"
            >
              <b-form-input
                id="code"
                v-model="code"
                type="text"
                class="py-4 mt-3 mb-2"
                :state="v$.code.$error ? false : null"
                :placeholder="$t('views.register.code')"
                @blur="v$.code.$touch"
              />
              <b-form-invalid-feedback
                v-if="v$.code.$error"
                id="codeError"
              >
                {{
                  $t(`validations.${v$.code.$errors[0].$validator}`, {
                    property: `${$t("forms.registration.code")}`,
                  })
                }}
              </b-form-invalid-feedback>
            </b-row>
            <b-row
              align-h="center"
              class="justify-content-center mt-2 mb-3"
            >
              <b-button
                type="submit"
                :disabled="loading"
                class="rounded-pill w-100 btn-green"
              >
                {{ $t("views.register.register") }}
              </b-button>
            </b-row>
            <b-row
              align-h="center"
              class="justify-content-center mt-3"
            >
              <b-button
                class="rounded-pill w-100 btn-red"
                @click="deleteSessionAndGoToLogin()"
              >
                {{ $t("views.cancel") }}
              </b-button>
            </b-row>
          </b-overlay>
        </b-form>
      </b-col>
    </b-row>
    <!-- Footer -->
    <b-row
      id="powered-by"
      align-h="center"
    >
      <PoweredBy />
    </b-row>
  </b-container>
</template>

<script>
import PoweredBy from '@/components/shared/PoweredBy.vue'
import Logo from '@/components/Logo.vue'
import { ref, computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
import * as cookies from 'tiny-cookie'

export default {
  name: 'Register',
  components: {
    Logo,
    PoweredBy
  },
  setup (props, context) {
    const $store = context.root.$store
    const errorMessage = computed(() => $store.getters.getPageErrorMessage)
    const loading = ref(false)
    const showDismissibleAlert = ref(false)
    const deleteSessionAndGoToLogin = () => {
      $store.dispatch('logout')
    }

    if (!cookies.getCookie('authorization')) {
      deleteSessionAndGoToLogin()
    }
    const code = ref('')
    const v$ = useVuelidate({
      code: {
        required
      }
    }, { code })
    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      loading.value = true
      $store.dispatch('register', code.value).then(() => {
        loading.value = false
      }).catch(e => {
        // console.log(e)
        showDismissibleAlert.value = true
        loading.value = false
        $store.dispatch('handleRegisterError', e)
      })
    }
    return {
      v$,
      submitForm,
      code,
      deleteSessionAndGoToLogin,
      errorMessage,
      loading,
      showDismissibleAlert
    }
  }
}
</script>
