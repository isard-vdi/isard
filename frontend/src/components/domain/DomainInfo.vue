<template>
  <span>
    <b-row>
      <!-- Name -->
      <b-col
        cols="4"
        xl="2"
      >
        <label for="name">{{ $t('forms.domain.info.name') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-form-input
          id="name"
          v-model="name"
          type="text"
          size="sm"
          :state="v$.name.$error ? false : null"
          @blur="v$.name.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.name.$error"
          id="nameError"
        >
          {{ $t(`validations.${v$.name.$errors[0].$validator}`, { property: $t('forms.domain.info.name'), model: name.length, min: 4, max: 50 }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>

    <!-- Description -->
    <b-row class="mt-4">
      <b-col
        cols="4"
        xl="2"
      >
        <label for="description">{{ $t('forms.domain.info.description') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-form-input
          id="description"
          v-model="description"
          type="text"
          maxlength="255"
          size="sm"
        />
        <b-form-invalid-feedback
          v-if="v$.description.$error"
          id="descriptionError"
        >
          {{ $t(`validations.${v$.description.$errors[0].$validator}`, { property: $t('forms.domain.info.description'), model: description.length, max: 255 }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>
  </span>
</template>

<script>
import { computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, maxLength, minLength } from '@vuelidate/validators'

// const inputFormat = helpers.regex('inputFormat', /^1(3|4|5|7|8)\d{9}$/) // /^\D*7(\D*\d){12}\D*$'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  setup (props, context) {
    const $store = context.root.$store
    const domain = computed(() => $store.getters.getDomain)
    const name = computed({
      get: () => $store.getters.getDomain.name,
      set: (value) => {
        domain.value.name = value
        $store.commit('setDomain', domain.value)
      }
    })
    const description = computed({
      get: () => $store.getters.getDomain.description,
      set: (value) => {
        domain.value.description = value
        $store.commit('setDomain', domain.value)
      }
    })
    return {
      name,
      description,
      v$: useVuelidate({
        name: {
          required,
          maxLengthValue: maxLength(50),
          minLengthValue: minLength(4),
          inputFormat
        },
        description: {
          maxLengthValue: maxLength(255)
        }
      }, { name, description })
    }
  }
}
</script>
