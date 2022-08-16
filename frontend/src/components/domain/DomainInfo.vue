<template>
  <div>
    <!-- Title -->
    <h4 class="my-4">
      <strong>{{ $t('forms.domain.info.title') }}</strong>
    </h4>

    <!-- Name -->
    <b-row>
      <b-col
        cols="4"
        xl="2"
      >
        <label for="nameField">{{ $t('forms.domain.info.name') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-form-input
          id="nameField"
          v-model="name"
          type="text"
          size="sm"
          @blur="v$.name.$touch"
        />
        <div
          v-if="v$.name.$error"
          class="isard-form-error"
        >
          {{ $t(`validations.${v$.name.$errors[0].$validator}`, { property: $t('forms.domain.info.name'), model: name.length, min: 4, max: 40 }) }}
        </div>
      </b-col>
    </b-row>

    <!-- Description -->
    <b-row class="mt-4">
      <b-col
        cols="4"
        xl="2"
      >
        <label for="domainDescriptionField">{{ $t('forms.domain.info.description') }}</label>
      </b-col>
      <b-col
        cols="6"
        xl="4"
      >
        <b-form-input
          id="domainDescriptionField"
          v-model="description"
          type="text"
          size="sm"
        />
      </b-col>
    </b-row>
  </div>
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
      v$: useVuelidate()
    }
  },
  validations () {
    return {
      name: {
        required,
        maxLengthValue: maxLength(40),
        minLengthValue: minLength(4),
        inputFormat
      }
    }
  }
}
</script>
