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
          <strong>{{ $t('forms.password.modal.title') }}</strong>
        </h4>

        <p
          v-if="!route.query.token && showUpdatePasswordForm"
          class="text-danger"
        >
          {{ $t(`forms.password.modal.warning`) }}
        </p>
        <UpdatePasswordForm v-if="showUpdatePasswordForm" />
        <b-row>
          <b-col cols="12">
            <b-alert
              :show="dismissCountDown"
              variant="success"
              @dismissed="dismissCountDown=0"
              @dismiss-count-down="countDownChanged"
            >
              {{ $t('views.reset-password.password-reset', { seconds: dismissCountDown }) }}
            </b-alert>
          </b-col>
        </b-row>
        <b-row align-h="end">
          <b-button
            size="md"
            class="btn-red rounded-pill mt-2"
            @click="logout()"
          >
            {{ $t(`views.maintenance.go-login`) }}
          </b-button>
          <b-button
            v-if="showUpdatePasswordForm"
            type="submit"
            size="md"
            class="btn-green rounded-pill mt-2 ml-2 mr-5"
          >
            {{ $t(`forms.password.modal.buttons.update`) }}
          </b-button>
        </b-row>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>
import { ref, computed, provide, onMounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, sameAs } from '@vuelidate/validators'
import UpdatePasswordForm from '@/components/UpdatePasswordForm'
import { StringUtils } from '../utils/stringUtils'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  components: {
    UpdatePasswordForm
  },
  setup (_, context) {
    const $store = context.root.$store
    const route = context.root.$route

    const password = computed(() => $store.getters.getPassword)
    const passwordConfirmation = computed(() => $store.getters.getPasswordConfirmation)

    const updatePasswordButtonDisabled = ref(false)
    const showUpdatePasswordForm = ref(true)

    onMounted(() => {
      if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token) && !route.query.token) {
        $store.dispatch('navigate', 'Login')
      } else {
        $store.dispatch('fetchExpiredPasswordPolicy', route.query.token ? route.query.token : localStorage.token)
      }
    })

    const v$ = useVuelidate({
      password: {
        required
      },
      passwordConfirmation: {
        required,
        sameAs: sameAs(password)
      }
    }, { password, passwordConfirmation })

    provide('vuelidate', v$)

    const submitForm = () => {
      updatePasswordButtonDisabled.value = true
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        updatePasswordButtonDisabled.value = false
        return
      }
      $store.dispatch('resetPassword', { token: route.query.token ? route.query.token : localStorage.token, password: password.value }).then(() => {
        showUpdatePasswordForm.value = false
        $store.dispatch('resetPasswordState')
        localStorage.removeItem('token')
        showAlert()
      }).catch((e) => {
        showUpdatePasswordForm.value = true
        ErrorUtils.showErrorMessage(context.root.$snotify, e)
        updatePasswordButtonDisabled.value = false
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

    return { password, passwordConfirmation, v$, submitForm, route, countDownChanged, dismissCountDown, updatePasswordButtonDisabled, logout, showUpdatePasswordForm }
  }
}
</script>
