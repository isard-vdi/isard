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
          <label for="urlField">{{ $t('forms.new-media.url') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-input
            id="urlField"
            v-model="url"
            type="text"
            size="sm"
            @blur="v$.url.$touch"
          />
          <div
            v-if="v$.url.$error"
            class="isard-form-error"
          >
            {{ $t(`validations.${v$.url.$errors[0].$validator}`, { property: $t('forms.new-media.url') }) }}
          </div>
        </b-col>
      </b-row>
      <!-- Name -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="nameField">{{ $t('forms.new-media.name') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
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
            {{ $t(`validations.${v$.name.$errors[0].$validator}`, { property: $t('forms.new-media.name'), model: name.length, min: 4, max: 40 }) }}
          </div>
        </b-col>
      </b-row>
      <!-- Description -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="descriptionField">{{ $t('forms.new-media.description') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-input
            id="descriptionField"
            v-model="description"
            type="text"
            size="sm"
          />
        </b-col>
      </b-row>
      <!-- Type -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="typeField">{{ $t('forms.new-media.type') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-select
            id="typeField"
            v-model="type"
            :options="mediaTypes"
            size="sm"
            @blur="v$.type.$touch"
          />
          <div
            v-if="v$.type.$error"
            class="isard-form-error"
          >
            {{ $t(`validations.${v$.type.$errors[0].$validator}`, { property: $t('forms.new-media.type') }) }}
          </div>
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
import { mapActions } from 'vuex'
import { ref, onUnmounted } from '@vue/composition-api'
import { required, minLength, maxLength, url } from '@vuelidate/validators'
import { map } from 'lodash'
import i18n from '@/i18n'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  components: {
    AllowedForm
  },
  setup (props, context) {
    const $store = context.root.$store

    const mediaTypes = ref([
      { value: null, text: i18n.t('forms.new-media.select-type'), disabled: true },
      { value: 'iso', text: 'ISO CD/DVD' },
      { value: 'floppy', text: 'Floppy' },
      { value: 'qcow2', text: 'Qcow2' }
    ])
    const url = ref('')
    const name = ref('')
    const description = ref('')
    const type = ref(null)

    onUnmounted(() => {
      $store.dispatch('resetMediaState')
    })

    return {
      url,
      name,
      description,
      type,
      mediaTypes,
      v$: useVuelidate()
    }
  },
  validations () {
    return {
      url: {
        required,
        url
      },
      type: {
        required
      },
      name: {
        required,
        maxLengthValue: maxLength(40),
        minLengthValue: minLength(4),
        inputFormat
      }
    }
  },
  methods: {
    ...mapActions([
      'createNewMedia',
      'navigate'
    ]),
    async submitForm () {
      const isFormCorrect = await this.v$.$validate()

      if (isFormCorrect) {
        const groups = this.groupsChecked ? map(this.selectedGroups, 'id') : false
        const users = this.usersChecked ? map(this.selectedUsers, 'id') : false
        this.createNewMedia(
          {
            name: this.name,
            description: this.description,
            allowed: {
              users,
              groups
            },
            kind: this.type,
            url: this.url,
            hypervisors_pools: ['default'] // TODO: Change harcoded
          }
        )
      }
    }
  }
}

</script>
