<template>
  <b-modal
    id="passwordModal"
    size="lg"
    :title="$t(`forms.password.modal.title`)"
    v-model="showPasswordModal"
    @hidden="closePasswordModal"
    centered
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <label for="password">{{ $t(`forms.password.modal.password.label`) }}</label>
        <b-form-input type="password" id="password" v-model="password" :placeholder="$t(`forms.password.modal.password.placeholder`)" @blur="v$.password.$touch"></b-form-input>
        <div class="isard-form-error" v-if="v$.password.$error">{{ $t(`validations.${v$.password.$errors[0].$validator}`, { property: $t('forms.password.modal.password.label'), model: password.length,  min: 4 }) }}</div>
      </b-col>
      <b-col cols="12" class="mt-2">
        <label for="confirmation-password">{{ $t(`forms.password.modal.confirmation-password.label`) }}</label>
        <b-form-input type="password" id="confirmation-password" v-model="passwordConfirmation" :placeholder="$t(`forms.password.modal.confirmation-password.placeholder`)"></b-form-input>
        <div class="isard-form-error" v-if="v$.passwordConfirmation.$error">{{ $t(`validations.${v$.passwordConfirmation.$errors[0].$validator}`, { property: `${$t("forms.password.modal.confirmation-password.label")}`, property2: `${$t("forms.password.modal.password.label")}` }) }}</div>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          variant="primary"
          class="float-right"
          @click="checkForm"
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

const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

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

    const showPasswordModal = computed({
      get: () => $store.getters.getShowPasswordModal,
      set: (value) => $store.commit('setShowPasswordModal', value)
    })

    const closePasswordModal = () => {
      $store.dispatch('resetPasswordState')
      $store.dispatch('showPasswordModal', false)
    }

    const updatePassword = () => {
      $store.dispatch('updatePassword', { password: password.value }).then(() => {
        closePasswordModal()
      })
    }

    return { password, passwordConfirmation, showPasswordModal, closePasswordModal, updatePassword, v$: useVuelidate() }
  },
  validations () {
    return {
      password: {
        required,
        minLengthValue: minLength(4),
        inputFormat
      },
      passwordConfirmation: {
        required,
        sameAs: sameAs(this.password)
      }
    }
  },
  methods: {
    async checkForm () {
      const isFormCorrect = await this.v$.$validate()

      if (isFormCorrect) {
        this.updatePassword()
      }
    }
  }
}
</script>
