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
              v-if="!['verified', 'error'].includes(alertType)"
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
              v-if="alertType"
              :show="dismissCountDown"
              :variant="alertVariant[alertType]"
              @dismissed="dismissCountDown=0"
              @dismiss-count-down="countDownChanged"
            >
              {{ $t(`views.verify-email.email-${alertType}`, { seconds: dismissCountDown }) }}
            </b-alert>
            <b-link
              v-if="['verified', 'error'].includes(alertType)"
              href="#foo"
              @click="logout(true)"
            >
              {{ $t('views.maintenance.go-login') }}
            </b-link>
          </b-col>
        </b-row>
        <b-row
          v-if="!['verified', 'error'].includes(alertType)"
          align-h="end"
        >
          <b-button
            size="md"
            class="btn-red rounded-pill mt-2"
            @click="logout(true)"
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
import { ref, computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, email } from '@vuelidate/validators'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const route = context.root.$route
    const user = computed(() => $store.getters.getUser)
    const emailAddress = ref(user.value ? user.value.current_email : null)
    const sendEmailButtonDisabled = ref(false)
    const alertType = ref('')

    const alertVariant = {
      verified: 'success',
      sent: 'warning',
      error: 'danger'
    }

    if (route.query.token) {
      $store.dispatch('updateSession', false)
      $store.dispatch('verifyEmail', route.query.token).then(() => {
        alertType.value = 'verified'
        showAlert()
      }).catch(() => {
        alertType.value = 'error'
        showAlert()
      })
    } else {
      emailAddress.value = user.value.current_email
    }

    const v$ = useVuelidate({
      emailAddress: {
        required,
        email
      }
    }, { emailAddress })

    const logout = (redirect) => {
      $store.dispatch('logout', redirect)
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
        $store.dispatch('updateSession', false)
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
        logout(true)
      }
    }
    const showAlert = () => {
      dismissCountDown.value = dismissSecs.value
    }

    return { emailAddress, v$, submitForm, user, logout, dismissCountDown, dismissSecs, countDownChanged, showAlert, alertType, sendEmailButtonDisabled, alertVariant }
  }
}
</script>
