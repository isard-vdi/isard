<template>
  <b-modal
    id="passwordModal"
    v-model="showPasswordModal"
    size="lg"
    :title="$t(`forms.password.modal.title`)"
    centered
    @hidden="closePasswordModal"
  >
    <UpdatePasswordForm />
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

    const password = computed(() => $store.getters.getPassword)
    const passwordConfirmation = computed(() => $store.getters.getPasswordConfirmation)
    const currentPassword = computed(() => $store.getters.getCurrentPassword)

    const v$ = useVuelidate({
      password: {
        required
      },
      passwordConfirmation: {
        required,
        sameAs: sameAs(password)
      },
      currentPassword: {
        required
      }
    }, { password, passwordConfirmation, currentPassword })

    provide('vuelidate', v$)

    const showPasswordModal = computed({
      get: () => $store.getters.getShowPasswordModal,
      set: (value) => $store.commit('setShowPasswordModal', value)
    })

    $store.dispatch('fetchPasswordPolicy')

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
      $store.dispatch('updatePassword', { password: password.value, current_password: currentPassword.value }).then((success) => {
        if (success) {
          closePasswordModal()
        }
      })
    }
    return { password, passwordConfirmation, showPasswordModal, closePasswordModal, v$, currentPassword, submitForm }
  }
}
</script>
