<template>
  <div>
    <!-- bastion check -->
    <b-row>
      <b-col cols="12">
        <div class="d-flex">
          <label
            for="checkbox-bastion"
            class="mr-2"
          ><b-icon
            icon="door-closed"
            class="mr-2"
            variant="danger"
          />{{ $t('forms.domain.viewers.bastion.disabled') }}</label>
          <b-form-checkbox
            id="checkbox-bastion"
            v-model="bastion"
            switch
          >
            <b-icon
              class="mr-2"
              icon="door-open"
              variant="success"
            />{{ $t('forms.domain.viewers.bastion.enabled') }}
          </b-form-checkbox>
        </div>
      </b-col>
    </b-row>
    <!-- Bastion Options -->
    <span
      v-if="showBastionOptions"
    >
      <h4>
        <strong>{{ $t('forms.domain.viewers.bastion.title') }}</strong>
      </h4>
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <b-form-checkbox
            id="checkbox-bastion-http"
            v-model="httpEnabled"
            switch
          >
            {{ $t('forms.domain.viewers.bastion.http.checkbox') }}
          </b-form-checkbox>
        </b-col>
      </b-row>
      <template v-if="httpEnabled">
        <b-row
          class="mt-2"
        >
          <b-col
            cols="4"
            xl="2"
          >
            <label for="httpPortsField">{{ $t('forms.domain.viewers.bastion.http.ports.label') }}</label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="httpPortsField"
              v-model="httpPorts"
              type="text"
              size="sm"
              :placeholder="$t('forms.domain.viewers.bastion.http.ports.placeholder')"
            />
            <!-- TODO: validate ints -->
          </b-col>
        </b-row>
      </template>
      <b-row
        class="mt-2"
      >
        <b-col
          cols="4"
          xl="2"
        >
          <b-form-checkbox
            id="checkbox-bastion-ssh"
            v-model="sshEnabled"
            switch
          >
            {{ $t('forms.domain.viewers.bastion.ssh.checkbox') }}
          </b-form-checkbox>
        </b-col>
      </b-row>
      <template v-if="sshEnabled">
        <b-row
          class="mt-2"
        >
          <b-col
            cols="4"
            xl="2"
          >
            <label for="sshPortsField">{{ $t('forms.domain.viewers.bastion.ssh.ports.label') }}</label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="sshPortsField"
              v-model="sshPorts"
              type="text"
              size="sm"
              :placeholder="$t('forms.domain.viewers.bastion.ssh.ports.placeholder')"
            />
            <!-- TODO: validate int -->
          </b-col>
        </b-row>
        <b-row
          class="mt-2 mb-4"
        >
          <b-col
            cols="4"
            xl="2"
          >
            <label
              for="sshAuthorizedKeysField"
              class="mb-0"
            >{{ $t('forms.domain.viewers.bastion.ssh.authorized_keys.label') }}</label>
            <!-- <b-form-checkbox
              id="checkbox-bastion-ssh-user"
              v-model="sshUser"
            >
              TODO: {{ $t('forms.domain.viewers.bastion.ssh.authorized_keys.user') }}
            </b-form-checkbox> -->
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-textarea
              id="sshAuthorizedKeysField"
              v-model="sshAuthorizedKeys"
              size="sm"
              rows="3"
              no-resize
              :placeholder="$t('forms.domain.viewers.bastion.ssh.authorized_keys.placeholder')"
            />
          </b-col>
        </b-row>
      </template>
    </span>
  </div>
</template>

<script>
import { computed, watch, ref } from '@vue/composition-api'

export default {
  setup (props, context) {
    const $store = context.root.$store
    // const domain = computed(() => $store.getters.getDomain)
    const bastionData = computed(() => $store.getters.getBastion)

    const showBastionOptions = ref(false)

    const bastion = computed({
      get: () => $store.getters.getBastion.enabled,
      set: (value) => {
        bastionData.value.enabled = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    watch(bastion, (newVal, prevVal) => {
      if (bastion.value) {
        showBastionOptions.value = true
      } else {
        showBastionOptions.value = false
      }
    })

    const httpEnabled = computed({
      get: () => $store.getters.getBastion.http.enabled,
      set: (value) => {
        bastionData.value.http.enabled = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const sshEnabled = computed({
      get: () => $store.getters.getBastion.ssh.enabled,
      set: (value) => {
        bastionData.value.ssh.enabled = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const splitComma = (text) => text.split(',')
    const httpPorts = computed({
      get: () => $store.getters.getBastion.http.port,
      set: (value) => {
        bastionData.value.http.port = splitComma(value)[0]
        $store.commit('setBastion', bastionData.value)
      }
    })
    const sshPorts = computed({
      get: () => $store.getters.getBastion.ssh.port,
      set: (value) => {
        bastionData.value.ssh.port = splitComma(value)[0]
        $store.commit('setBastion', bastionData.value)
      }
    })
    const splitNewLine = (text) => text.split(/\r?\n/)
    const joinNewLine = (array) => array.join('\n')
    const sshAuthorizedKeys = computed({
      get: () => joinNewLine($store.getters.getBastion.ssh.authorized_keys),
      set: (value) => {
        bastionData.value.ssh.authorized_keys = splitNewLine(value)
        $store.commit('setBastion', bastionData.value)
      }
    })
    // const sshUser = ref(true) // TODO: user keys in db user

    return {
      showBastionOptions,
      bastion,
      httpEnabled,
      httpPorts,
      sshEnabled,
      sshPorts,
      // sshUser,
      sshAuthorizedKeys
    }
  }
}
</script>
