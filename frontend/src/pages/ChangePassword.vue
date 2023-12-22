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
        <UpdatePasswordForm />
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
import { computed, provide } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, sameAs } from '@vuelidate/validators'
import UpdatePasswordForm from '@/components/UpdatePasswordForm'

export default {
  components: {
    UpdatePasswordForm
  },
  setup (_, context) {
    const $store = context.root.$store
    const route = context.root.$route

    const password = computed(() => $store.getters.getPassword)
    const passwordConfirmation = computed(() => $store.getters.getPasswordConfirmation)

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
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      $store.dispatch('updateForgottenPassword', { token: route.query.token, password: password.value })
    }

    return { password, passwordConfirmation, v$, submitForm }
  }
}
</script>
