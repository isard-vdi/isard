<template>
  <b-modal
    id="emailVerificationModal"
    v-model="showEmailVerificationModal"
    size="lg"
    :title="$t(`forms.email.modal.title`)"
    centered
    hide-footer
    @hidden="closeEmailVerificationModal"
  >
    <b-row class="h-100 justify-content-center">
      <b-avatar
        icon="envelope-open-fill"
        size="7rem"
      />
    </b-row>
    <b-row class="justify-content-center m-2">
      <h4 class="font-weight-bold">
        {{ $t(`forms.email.modal.change-validate-address`) }}
      </h4>
    </b-row>
    <b-col
      class="justify-content-center verification-content"
    >
      <label for="emailAddress">{{ $t(`forms.email.modal.email.label`) }}</label>
      <b-form-input
        id="emailAddress"
        v-model="emailAddress"
        type="text"
        autocomplete="off"
        :placeholder="$t(`forms.email.modal.email.placeholder`)"
        :state="v$.emailAddress.$error ? false : null"
        @blur="v$.emailAddress.$touch"
      />
      <b-form-invalid-feedback
        v-if="v$.emailAddress.$error"
        id="emailAddress"
      >
        {{ $t(`validations.${v$.emailAddress.$errors[0].$validator}`, { property: $t('forms.email.modal.email.label') }) }}
      </b-form-invalid-feedback>
    </b-col>
    <b-row class="justify-content-center">
      <b-button
        class="rounded-pill m-2 pl-2 pr-2 btn-blue"
        title=""
        @click="submitForm"
      >
        <b-icon
          icon="check-circle-fill"
          scale="0.85"
        />
        {{ $t(`forms.email.modal.buttons.verify`) }}
      </b-button>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, email } from '@vuelidate/validators'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const emailAddress = computed({
      get: () => $store.getters.getEmailAddress,
      set: (value) => $store.commit('setEmailAddress', value)
    })

    const v$ = useVuelidate({
      emailAddress: {
        required,
        email
      }
    }, { emailAddress })

    const showEmailVerificationModal = computed({
      get: () => $store.getters.getShowEmailVerificationModal,
      set: (value) => $store.commit('setShowEmailVerificationModal', value)
    })

    const closeEmailVerificationModal = () => {
      $store.dispatch('resetEmailAddressState')
      $store.dispatch('showEmailVerificationModal', false)
    }

    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
      }
      $store.dispatch('updateEmail', { email: emailAddress.value }).then(() => {
        closeEmailVerificationModal()
      })
    }

    return { emailAddress, showEmailVerificationModal, closeEmailVerificationModal, v$, submitForm }
  }
}
</script>
