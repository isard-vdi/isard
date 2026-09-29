<template>
  <div class="my-2">
    <!-- Title -->
    <h4>
      <strong>
        {{ $t('forms.domain.guest.title') }}
      </strong>
    </h4>
    <p class="text-danger font-weight-bold">
      <b-icon
        class="mr-2"
        variant="danger"
        icon="exclamation-triangle-fill"
      />
      {{ $t('forms.domain.guest.warning') }}
    </p>
    <p v-if="canUseBastion">
      {{ $t('forms.domain.guest.rdp-bastion') }}
    </p>
    <b-row>
      <b-col
        cols="4"
        xl="2"
      >
        <label for="usernameField">{{ $t('forms.domain.guest.username') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-form-input
          id="usernameField"
          v-model="username"
          type="text"
          size="sm"
          :state="v$.usernameField.$error ? false : null"
          @blur="v$.usernameField.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.usernameField.$error"
          id="usernameFieldError"
        >
          {{ $t(`validations.${v$.usernameField.$errors[0].$validator}`, { property: $t('forms.domain.guest.username') }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>
    <b-row class="mt-4">
      <!-- Guest password -->
      <b-col
        cols="4"
        xl="2"
      >
        <label for="passwordField">{{ $t('forms.domain.guest.password') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-input-group
          title="Show password"
          size="sm"
          @click="togglePassword()"
        >
          <template #append>
            <b-input-group-text
              v-b-tooltip.hover
              class="cursor-pointer"
            >
              <b-icon
                :icon="showPassword ? 'eye' : 'eye-slash'"
                aria-hidden="true"
                class="text-medium-gray"
              />
            </b-input-group-text>
          </template>
          <b-form-input
            id="passwordField"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
            size="sm"
            :state="v$.passwordField.$error ? false : null"
            @blur="v$.passwordField.$touch"
          />
        </b-input-group>
        <b-form-invalid-feedback
          v-if="v$.passwordField.$error"
          id="passwordFieldError"
          :force-show="true"
        >
          {{ $t(`validations.${v$.passwordField.$errors[0].$validator}`, { property: $t('forms.domain.guest.password') }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>
  </div>
</template>
<script>
import { computed, ref } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'

export default {
  props: {
    canUseBastion: {
      type: Boolean,
      required: true
    }
  },
  setup (props, context) {
    const $store = context.root.$store
    const showPassword = ref(false)
    const domain = computed(() => $store.getters.getDomain)
    const username = computed({
      get: () => $store.getters.getDomain.guestProperties.credentials.username,
      set: (value) => {
        domain.value.guestProperties.credentials.username = value
        $store.commit('setDomain', domain.value)
      }
    })
    const password = computed({
      get: () => $store.getters.getDomain.guestProperties.credentials.password,
      set: (value) => {
        domain.value.guestProperties.credentials.password = value
        $store.commit('setDomain', domain.value)
      }
    })
    return {
      username,
      password,
      showPassword,
      v$: useVuelidate({
        usernameField: { required },
        passwordField: { required }
      }, { usernameField: username, passwordField: password }),
      togglePassword () {
        this.showPassword = !this.showPassword
      }
    }
  }
}
</script>
