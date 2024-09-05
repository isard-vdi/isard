<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5"
  >
    <b-form @submit.prevent="submitForm">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.new-media.title') }}</strong>
        </h4>
      </b-row>
      <!-- Url -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="mediaUrl">{{ $t('forms.new-media.url') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-input
            id="mediaUrl"
            v-model="mediaUrl"
            type="text"
            size="sm"
            :state="v$.mediaUrl.$error ? false : null"
            @blur="v$.mediaUrl.$touch"
          />
          <b-form-invalid-feedback
            v-if="v$.mediaUrl.$error"
            id="mediaUrlError"
          >
            {{ $t(`validations.${v$.mediaUrl.$errors[0].$validator}`, { property: $t('forms.new-media.url') }) }}
          </b-form-invalid-feedback>
        </b-col>
      </b-row>
      <!-- Name -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="name">{{ $t('forms.new-media.name') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
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
            {{ $t(`validations.${v$.name.$errors[0].$validator}`, { property: $t('forms.new-media.name'), model: name.length, min: 4, max: 50 }) }}
          </b-form-invalid-feedback>
        </b-col>
      </b-row>
      <!-- Description -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="description">{{ $t('forms.new-media.description') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
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
      <!-- Type -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="type">{{ $t('forms.new-media.type') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-select
            id="type"
            v-model="type"
            :options="mediaTypes"
            size="sm"
            :state="v$.type.$error ? false : null"
            @blur="v$.type.$touch"
          />
          <b-form-invalid-feedback
            v-if="v$.type.$error"
            id="typeError"
          >
            {{ $t(`validations.${v$.type.$errors[0].$validator}`, { property: $t('forms.new-media.type') }) }}
          </b-form-invalid-feedback>
        </b-col>
      </b-row>
      <b-row clas="mt-2">
        <h4 class="p-1 mb-2 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.allowed.title') }}</strong>
        </h4>
      </b-row>
      <!-- Allowed -->
      <AllowedForm />
      <!-- Buttons -->
      <b-row align-h="end">
        <b-button
          size="md"
          class="btn-red rounded-pill mt-4 mr-2"
          @click="navigate('media')"
        >
          {{ $t('forms.cancel') }}
        </b-button>
        <b-button
          type="submit"
          size="md"
          class="btn-green rounded-pill mt-4 ml-2 mr-5"
        >
          {{ $t('forms.create') }}
        </b-button>
      </b-row>
    </b-form>
  </b-container>
</template>

<script>
import AllowedForm from '@/components/AllowedForm.vue'

import useVuelidate from '@vuelidate/core'
import { ref, onUnmounted, computed } from '@vue/composition-api'
import { required, minLength, maxLength, url } from '@vuelidate/validators'
import { map } from 'lodash'
import i18n from '@/i18n'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)
const URLFormat = value => /^https:\/\/[a-zA-Z0-9.-_~:/?#[\]@!$&'()*+,;=%]+(?:\/[a-zA-Z0-9.-_~:/?#[\]@!$&'()*+,;=%]+)*(?:\/)?[^\s?#]+(?:\?.*)?$/.test(value)

export default {
  components: {
    AllowedForm
  },
  setup (props, context) {
    const $store = context.root.$store
    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }

    const mediaTypes = ref([
      { value: null, text: i18n.t('forms.new-media.select-type'), disabled: true },
      { value: 'iso', text: 'ISO CD/DVD' },
      { value: 'floppy', text: 'Floppy' }
    ])
    const mediaUrl = ref('')
    const name = ref('')
    const description = ref('')
    const type = ref(null)
    const groupsChecked = computed(() => $store.getters.getGroupsChecked)
    const selectedGroups = computed(() => $store.getters.getSelectedGroups)
    const usersChecked = computed(() => $store.getters.getUsersChecked)
    const selectedUsers = computed(() => $store.getters.getSelectedUsers)

    const v$ = useVuelidate({
      mediaUrl: {
        required,
        url,
        URLFormat
      },
      type: {
        required
      },
      name: {
        required,
        maxLengthValue: maxLength(50),
        minLengthValue: minLength(4),
        inputFormat
      },
      description: {
        maxLengthValue: maxLength(255)
      }
    }, { mediaUrl, type, name, description })

    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      const groups = groupsChecked.value ? map(selectedGroups.value, 'id') : false
      const users = usersChecked.value ? map(selectedUsers.value, 'id') : false
      $store.dispatch('createNewMedia',
        {
          name: name.value,
          description: description.value,
          allowed: {
            users,
            groups
          },
          kind: type.value,
          url: mediaUrl.value,
          hypervisors_pools: ['default'] // TODO: Change harcoded
        }
      )
    }

    onUnmounted(() => {
      $store.dispatch('resetMediaState')
      $store.dispatch('resetAllowedState')
    })

    return {
      mediaUrl,
      name,
      description,
      type,
      mediaTypes,
      v$,
      submitForm,
      navigate
    }
  }
}
</script>
