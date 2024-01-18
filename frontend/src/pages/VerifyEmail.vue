<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pb-5"
  >
    <b-row class="justify-content-center">
      <b-form
        class="w-25"
        @submit.prevent="submitForm"
      >
        <h4>
          <strong>{{ $t('views.verify-email.title') }}</strong>
        </h4>
        <b-row>
          <b-col
            cols="12"
          >
            <b-form-group
              v-if="alertType !== 'verified'"
              :description="$t('views.verify-email.description')"
            >
              <label for="emailAddress">{{ $t(`views.verify-email.label`) }}</label>
              <b-form-input
                id="emailAddress"
                v-model="emailAddress"
                autocomplete="off"
                :autofocus="true"
                :placeholder="$t('views.verify-email.placeholder')"
                :state="v$.emailAddress.$error ? false : null"
                @blur="v$.emailAddress.$touch"
              />
              <b-form-invalid-feedback
                v-if="v$.emailAddress.$error"
                id="emailAddressError"
              >
                {{ $t(`validations.${v$.emailAddress.$errors[0].$validator}`, { property: $t('views.verify-email.label') }) }}
              </b-form-invalid-feedback>
            </b-form-group>
            <b-alert
              :show="dismissCountDown"
              :variant="alertType === 'verified' ? 'success' : 'warning'"
              @dismissed="dismissCountDown=0"
              @dismiss-count-down="countDownChanged"
            >
              {{ $t(`views.verify-email.email-${alertType}`, { seconds: dismissCountDown }) }}
            </b-alert>
            <b-link
              v-if="alertType === 'verified'"
              href="#foo"
              @click="logout()"
            >
              {{ $t('views.maintenance.go-login') }}
            </b-link>
          </b-col>
        </b-row>
        <b-row
          v-if="alertType !== 'verified'"
          align-h="end"
        >
          <b-button
            size="md"
            class="btn-red rounded-pill mt-2"
            @click="logout()"
          >
            {{ $t(`views.maintenance.go-login`) }}
          </b-button>
          <b-button
            type="submit"
            size="md"
            class="btn-green rounded-pill mt-2 ml-2 mr-3"
            :disabled="sendEmailButtonDisabled"
          >
            {{ $t('views.verify-email.send-verify-email') }}
          </b-button>
        </b-row>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>
import { ref, computed, onMounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, email } from '@vuelidate/validators'
import { StringUtils } from '../utils/stringUtils'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const user = computed(() => $store.getters.getUser)

    const emailAddress = ref(user.value.current_email)

    const sendEmailButtonDisabled = ref(false)

    const alertType = ref('')

    onMounted(() => {
      if (context.root.$route.query.token) {
        $store.dispatch('verifyEmail', context.root.$route.query.token).then(() => {
          localStorage.token = ''
          alertType.value = 'verified'
          showAlert()
        })
      } else if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token)) {
        $store.dispatch('navigate', 'Login')
      } else {
        $store.dispatch('setSession', localStorage.token)
        emailAddress.value = user.value.current_email
      }
    })

    const v$ = useVuelidate({
      emailAddress: {
        required,
        email
      }
    }, { emailAddress })

    const logout = () => {
      $store.dispatch('logout')
    }

    const submitForm = () => {
      sendEmailButtonDisabled.value = true
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        sendEmailButtonDisabled.value = false
        return
      }
      $store.dispatch('sendVerifyEmail', { email: emailAddress.value }).then(() => {
        localStorage.removeItem('token')
        alertType.value = 'sent'
        showAlert()
      }).catch((e) => {
        ErrorUtils.showErrorMessage(context.root.$snotify, e)
        sendEmailButtonDisabled.value = false
      })
    }

    const dismissSecs = ref(10)
    const dismissCountDown = ref(0)

    const countDownChanged = (countDown) => {
      dismissCountDown.value = countDown
      if (countDown === 0) {
        $store.dispatch('logout')
      }
    }
    const showAlert = () => {
      dismissCountDown.value = dismissSecs.value
    }

    return { emailAddress, v$, submitForm, user, logout, dismissCountDown, dismissSecs, countDownChanged, showAlert, alertType, sendEmailButtonDisabled }
  }
}
</script>
