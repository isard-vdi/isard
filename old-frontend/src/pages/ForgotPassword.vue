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
        <h4 class="p-1 mb-2 mt-2 ml-2">
          <strong>{{ $t('views.forgot-password.title') }}</strong>
        </h4>
        <b-col
          cols="12"
        >
          <b-form-group
            :description="$t('views.forgot-password.description')"
          >
            <label for="emailAddress">{{ $t(`views.forgot-password.label`) }}</label>
            <b-form-input
              id="emailAddress"
              v-model="emailAddress"
              :placeholder="$t('views.forgot-password.placeholder')"
              :state="v$.emailAddress.$error ? false : null"
              autocomplete="off"
              :autofocus="true"
              @blur="v$.emailAddress.$touch"
            />
            <b-form-invalid-feedback
              v-if="v$.emailAddress.$error"
              id="emailAddressError"
            >
              {{ $t(`validations.${v$.emailAddress.$errors[0].$validator}`, { property: $t('views.forgot-password.label') }) }}
            </b-form-invalid-feedback>
          </b-form-group>
          <b-alert
            :show="dismissCountDown"
            variant="warning"
            @dismissed="dismissCountDown=0"
            @dismiss-count-down="countDownChanged"
          >
            {{ $t('views.forgot-password.email-sent', { seconds: dismissCountDown }) }}
          </b-alert>
        </b-col>
        <b-row align-h="end">
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
            {{ $t(`views.forgot-password.reset-password`) }}
          </b-button>
        </b-row>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>
import { ref } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, email } from '@vuelidate/validators'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const route = context.root.$route

    const emailAddress = ref('')
    const category = route.query.categoryId
    const sendEmailButtonDisabled = ref(false)

    const v$ = useVuelidate({
      emailAddress: {
        required,
        email
      }
    }, { emailAddress })

    const submitForm = () => {
      sendEmailButtonDisabled.value = true
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        sendEmailButtonDisabled.value = false
        return
      }
      $store.dispatch('sendResetPasswordEmail', { email: emailAddress.value, category_id: category }).then(() => {
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

    const logout = () => {
      $store.dispatch('logout')
    }

    return { emailAddress, v$, submitForm, countDownChanged, dismissCountDown, sendEmailButtonDisabled, logout }
  }
}
</script>
