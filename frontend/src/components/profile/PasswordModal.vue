<template>
  <b-modal
    id="passwordModal"
    v-model="showPasswordModal"
    size="lg"
    :title="$t(`forms.password.modal.title`)"
    centered
    @hidden="closePasswordModal"
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <label for="password">{{ $t(`forms.password.modal.password.label`) }}</label>
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
        class="mt-2"
      >
        <label for="confirmation-password">{{ $t(`forms.password.modal.confirmation-password.label`) }}</label>
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
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          variant="primary"
          class="float-right"
          @click="submitForm"
        >
          {{ $t(`forms.password.modal.buttons.update`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, minLength, sameAs } from '@vuelidate/validators'

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
        required,
        minLengthValue: minLength(8)
      },
      passwordConfirmation: {
        required,
        sameAs: sameAs(password)
      }
    }, { password, passwordConfirmation })

    const showPasswordModal = computed({
      get: () => $store.getters.getShowPasswordModal,
      set: (value) => $store.commit('setShowPasswordModal', value)
    })

    const closePasswordModal = () => {
      $store.dispatch('resetPasswordState')
      $store.dispatch('showPasswordModal', false)
    }

    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      $store.dispatch('updatePassword', { password: password.value }).then(() => {
        closePasswordModal()
      })
    }

    return { password, passwordConfirmation, showPasswordModal, closePasswordModal, v$, submitForm }
  }
}
</script>
