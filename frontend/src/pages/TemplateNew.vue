<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5"
  >
    <b-form @submit.prevent="submitForm">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.new-template.title') }}</strong>
        </h4>
      </b-row>

      <!-- Name -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="nameField">{{ $t('forms.new-template.name') }}</label>
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
            {{ $t(`validations.${v$.desktop.$errors[0].$validator}`, { property: $t('forms.new-template.name'), model: name.length, min: 4, max: 40 }) }}
          </div>
        </b-col>
      </b-row>

      <!-- Description -->
      <b-row class="mt-4">
        <b-col
          cols="4"
          xl="2"
        >
          <label for="descriptionField">{{ $t('forms.new-template.description') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
        >
          <b-form-input
            id="descriptionField"
            v-model="description"
            type="text"
            size="sm"
          />
        </b-col>
      </b-row>

      <!-- Enabled -->
      <b-row>
        <b-col cols="12">
          <div class="d-flex">
            <label
              for="switch_1"
              class="mr-2"
            ><b-icon
              icon="eye-slash-fill"
              class="mr-2"
              variant="danger"
            />{{ $t('forms.new-template.disabled') }}</label>
            <b-form-checkbox
              id="checkbox-1"
              v-model="enabled"
              switch
            >
              <b-icon
                class="mr-2"
                icon="eye-fill"
                variant="success"
              />{{ $t('forms.new-template.enabled') }}
            </b-form-checkbox>
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
          @click="navigate('desktops')"
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
import { ref, computed, onUnmounted } from '@vue/composition-api'
import { mapActions, mapGetters } from 'vuex'
import useVuelidate from '@vuelidate/core'
import { required, maxLength, minLength } from '@vuelidate/validators'
import AllowedForm from '@/components/AllowedForm.vue'
import { map } from 'lodash'

const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  components: {
    AllowedForm
  },
  setup (props, context) {
    const $store = context.root.$store

    const name = ref('')
    const description = ref('')
    const enabled = ref(true)

    const groupsChecked = computed(() => $store.getters.getGroupsChecked)
    const selectedGroups = computed(() => $store.getters.getSelectedGroups)
    const usersChecked = computed(() => $store.getters.getUsersChecked)
    const selectedUsers = computed(() => $store.getters.getSelectedUsers)

    onUnmounted(() => {
      $store.dispatch('resetAllowedState')
    })

    return {
      name,
      description,
      enabled,
      groupsChecked,
      selectedGroups,
      usersChecked,
      selectedUsers,
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
  },
  computed: {
    ...mapGetters([
      'getTemplateNewItemId'
    ])
  },
  mounted () {
    if (this.getTemplateNewItemId.length < 1) {
      this.navigate('desktops')
    }
  },
  methods: {
    ...mapActions([
      'createNewTemplate',
      'navigate'
    ]),
    async submitForm () {
      const isFormCorrect = await this.v$.$validate()

      if (isFormCorrect) {
        const groups = this.groupsChecked ? map(this.selectedGroups, 'id') : false
        const users = this.usersChecked ? map(this.selectedUsers, 'id') : false
        this.createNewTemplate(
          {
            desktop_id: this.getTemplateNewItemId,
            name: this.name,
            description: this.description,
            allowed: {
              users,
              groups
            },
            enabled: this.enabled
          }
        )
      }
    }
  }
}
</script>
