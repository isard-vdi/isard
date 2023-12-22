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
            <strong>{{ $t('views.forgot-password.title') }}</strong>
          </h4>
        </b-row>
        <b-col
          cols="12"
          class="mb-4"
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
              @blur="v$.emailAddress.$touch"
            />
            <b-form-invalid-feedback
              v-if="v$.emailAddress.$error"
              id="emailAddressError"
            >
              {{ $t(`validations.${v$.emailAddress.$errors[0].$validator}`, { property: $t('views.forgot-password.label') }) }}
            </b-form-invalid-feedback>
          </b-form-group>
        </b-col>
        <b-row align-h="end">
          <b-button
            type="submit"
            size="md"
            class="btn-green rounded-pill mt-4 ml-2 mr-5"
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

export default {
  setup (_, context) {
    const $store = context.root.$store
    const route = context.root.$route

    const emailAddress = ref('')
    const category = route.query.categoryId

    const v$ = useVuelidate({
      emailAddress: {
        required,
        email
      }
    }, { emailAddress })

    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      $store.dispatch('sendResetPasswordEmail', { email: emailAddress.value, category_id: category })
    }

    return { emailAddress, v$, submitForm }
  }
}
</script>
