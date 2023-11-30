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
        <b-row class="mt-2">
          <h4 class="p-1 mb-2 mt-2 ml-2">
            <strong>{{ $t('forms.password.modal.title') }}</strong>
          </h4>
        </b-row>

        <b-row
          class="text-danger mb-4 p-1 ml-2"
        >
          {{ $t(`forms.password.modal.warning`) }}
        </b-row>

        <b-col
          cols="12"
        >
          <label for="password">{{ $t(`forms.password.modal.password.label`) }}</label>
        </b-col>
        <b-col
          cols="12"
          class="mb-4"
        >
          <b-form-input
            id="password"
            v-model="password"
            type="password"
            :placeholder="$t(`forms.password.modal.password.placeholder`)"
            :state="v$.password.$error ? false : null"
            @blur="v$.password.$touch"
          />
          <b-form-invalid-feedback
            v-if="v$.password.$error"
            id="passwordError"
          >
            {{ $t(`validations.${v$.password.$errors[0].$validator}`, { property: $t('forms.password.modal.password.label'), model: password.length, min: 8 }) }}
          </b-form-invalid-feedback>
        </b-col>
        <b-col
          cols="12"
        >
          <label for="confirmation-password">{{ $t(`forms.password.modal.confirmation-password.label`) }}</label>
        </b-col>
        <b-col
          cols="12"
          class="mb-4"
        >
          <b-form-input
            id="passwordConfirmation"
            v-model="passwordConfirmation"
            type="password"
            :placeholder="$t(`forms.password.modal.confirmation-password.placeholder`)"
            :state="v$.passwordConfirmation.$error ? false : null"
            @blur="v$.passwordConfirmation.$touch"
          />
          <b-form-invalid-feedback
            v-if="v$.passwordConfirmation.$error"
            id="passwordConfirmationError"
          >
            {{ $t(`validations.${v$.passwordConfirmation.$errors[0].$validator}`, { property: `${$t("forms.password.modal.confirmation-password.label")}`, property2: `${$t("forms.password.modal.password.label")}` }) }}
          </b-form-invalid-feedback>
        </b-col>
        <b-row align-h="end">
          <b-button
            type="submit"
            size="md"
            class="btn-green rounded-pill mt-4 ml-2 mr-5"
          >
            {{ $t(`forms.password.modal.buttons.update`) }}
          </b-button>
        </b-row>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>
import { computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, sameAs } from '@vuelidate/validators'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const password = computed({
      get: () => $store.getters.getPassword,
      set: (value) => $store.commit('setPassword', value)
    })

    const passwordConfirmation = computed({
      get: () => $store.getters.getPasswordConfirmation,
      set: (value) => $store.commit('setPasswordConfirmation', value)
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

    // const closePasswordModal = () => {
    //   $store.dispatch('resetPasswordState')
    //   $store.dispatch('showPasswordModal', false)
    // }

    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      $store.dispatch('updatePassword', { password: password.value }).then((success) => {
        if (success) {
        //  TODO: update password and send to login page or main page
        }
      })
    }

    return { password, passwordConfirmation, v$, submitForm }
  }
}
</script>
