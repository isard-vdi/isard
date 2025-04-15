<template>
  <b-modal
    id="importUserModal"
    v-model="showApiKeyModal"
    size="lg"
    :title="$t(`forms.api-key.modal.title`)"
    centered
    header-class="bg-purple text-white"
    hide-footer
    @hidden="closeImportUserModal"
  >
    <b-alert
      :show="alertKind === 'regenerated'"
      variant="info"
      class="mx-4"
    >
      {{ $t(`forms.api-key.modal.alert.regenerated`) }}
    </b-alert>
    <b-alert
      :show="alertKind === 'expired'"
      variant="danger"
      class="mx-4"
    >
      {{ $t(`forms.api-key.modal.alert.expired`) }}
    </b-alert>

    <template v-if="!userApiKey.exists || userApiKey.key">
      <!-- User doesn't have an API key or just generated a new one. -->
      <b-row
        class="ml-2 mr-2"
      >
        <b-col cols="12">
          <h5>
            {{ $t(`forms.api-key.modal.new-key.title`) }}
          </h5>
          <b-row
            class="mx-3 mt-3"
          >
            <p>
              {{ $t(`forms.api-key.modal.new-key.description`) }}
            </p>
          </b-row>

          <template v-if="!userApiKey.key">
            <b-row class="mx-3 mb-2">
              <b-col class="ml-0 pl-0">
                <label
                  for="datepicker-invalid"
                  class="mb-0"
                >
                  {{ $t(`forms.api-key.modal.new-key.buttons.expiration-label`) }}
                </label>
                <b-form-datepicker
                  v-model="apiKeyMaxDate"
                  value-as-date
                  :max="new Date(new Date().setFullYear(new Date().getFullYear() + 1))"
                  :min="new Date()"
                  :locale="$i18n.locale"
                />
              </b-col>
              <b-button
                variant="purple"
                class="mt-auto"
                :title="$t(`forms.api-key.modal.new-key.buttons.generate-tooltip`)"
                @click="submitGenerateKey"
              >
                {{ $t(`forms.api-key.modal.new-key.buttons.generate`) }}
              </b-button>
            </b-row>
          </template>
          <template v-else>
            <!-- User generated a new API key. -->
            <p class="mb-1">
              {{ $t(`forms.api-key.modal.new-key.warning`) }}
            </p>
            <b-input-group
              id=""
              class="mb-2"
            >
              <b-form-input
                readonly
                :value="userApiKey.key"
                :type="showApiKey ? 'text' : 'password'"
              />
              <b-input-group-append>
                <b-button
                  :title="$t('forms.api-key.modal.new-key.buttons.show')"
                  @click="showApiKey = !showApiKey"
                >
                  <b-icon
                    :icon="showApiKey ? 'eye-slash' : 'eye'"
                  />
                </b-button>
                <b-button
                  :title="$t('forms.api-key.modal.new-key.buttons.copy')"
                  @click="copyToClipboard(userApiKey.key)"
                >
                  <b-icon
                    icon="clipboard"
                  />
                </b-button>
              </b-input-group-append>
            </b-input-group>
          </template>
        </b-col>
      </b-row>
    </template>
    <template v-else>
      <!-- User already has an API key. -->
      <b-row
        class="ml-2 mr-2"
      >
        <b-col cols="12">
          <b-row
            class="mx-3"
          >
            <p>
              {{ $t(`forms.api-key.modal.existing-key.description-1`, { date: userApiKey.expireDate }) }}
            </p>
            <br>
            <p>
              {{ $t(`forms.api-key.modal.existing-key.description-2`) }}
            </p>
          </b-row>

          <b-row class="ml-3 mb-2">
            <b-button
              variant="danger"
              class=""
              :title="$t(`forms.api-key.modal.existing-key.buttons.expire-tooltip`)"
              @click="submitExpireKey"
            >
              {{ $t(`forms.api-key.modal.existing-key.buttons.expire`) }}
            </b-button>
          </b-row>
        </b-col>
      </b-row>
    </template>
  </b-modal>
</template>

<script>
import { computed, ref, watch } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const userApiKey = computed(() => $store.getters.getUserApiKey)
    watch(() => userApiKey.value.expireDate, (newVal) => {
      if (userApiKey.value.exists && new Date(newVal) < new Date()) {
        alertKind.value = 'expired'
      }
    })

    const apiKeyMaxDate = ref(new Date(new Date().setMonth(new Date().getMonth() + 1)))
    const alertKind = ref('')
    const showApiKey = ref(false)

    const showApiKeyModal = computed({
      get: () => $store.getters.getShowApiKeyModal,
      set: (value) => $store.commit('setShowApiKeyModal', value)
    })

    const submitGenerateKey = () => {
      $store.dispatch('generateApiKey', apiKeyMaxDate.value)
    }

    const submitExpireKey = () => {
      $store.dispatch('expireApiKey')
    }

    const closeImportUserModal = () => {
      alertKind.value = ''
      showApiKeyModal.value = false
      $store.commit('resetUserApiKey')
      $store.dispatch('showApiKeyModal', false)
    }

    const copyToClipboard = (text) => {
      navigator.clipboard.writeText(text)
      $store.dispatch('showNotification', { message: i18n.t('forms.api-key.modal.new-key.buttons.key-copied') })
    }

    return {
      userApiKey,
      apiKeyMaxDate,
      alertKind,
      showApiKey,
      submitGenerateKey,
      submitExpireKey,
      showApiKeyModal,
      closeImportUserModal,
      copyToClipboard
    }
  }
}
</script>
