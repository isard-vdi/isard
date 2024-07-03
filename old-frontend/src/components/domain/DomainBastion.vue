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
        <h5
          v-if="bastionId"
          v-b-tooltip="{ title: `${copyTooltipText}`,
                         placement: 'top',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          class="cursor-pointer"
          @click="copyToClipboard(bastionId)"
        >
          <b>ID:</b> {{ bastionId }}
        </h5>
      </b-row>
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
            <label for="httpPortField">{{ $t('forms.domain.viewers.bastion.http.http_port') }}</label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="httpPortField"
              v-model="httpPort"
              type="number"
              size="sm"
              placeholder="80"
            />
          </b-col>
        </b-row>

        <b-row
          class="mt-2"
        >
          <b-col
            cols="4"
            xl="2"
          >
            <label for="httpPortField">{{ $t('forms.domain.viewers.bastion.http.https_port') }}</label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="httpsPortField"
              v-model="httpsPort"
              type="number"
              size="sm"
              placeholder="443"
            />
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
            <label for="sshPortField">{{ $t('forms.domain.viewers.bastion.ssh.port') }}</label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="sshPortField"
              v-model="sshPort"
              type="number"
              size="sm"
              placeholder="22"
            />
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
            >{{ $t('forms.domain.viewers.bastion.ssh.authorized_keys') }}</label>
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
              placeholder="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7..."
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
        if (!value) {
          bastionData.value.http.enabled = false
          bastionData.value.ssh.enabled = false
        }
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

    const bastionId = computed({
      get: () => $store.getters.getBastion.id
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
    const httpPort = computed({
      get: () => $store.getters.getBastion.http.http_port,
      set: (value) => {
        bastionData.value.http.port = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const httpsPort = computed({
      get: () => $store.getters.getBastion.http.https_port,
      set: (value) => {
        bastionData.value.http.port = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const sshPort = computed({
      get: () => $store.getters.getBastion.ssh.port,
      set: (value) => {
        bastionData.value.ssh.port = value
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
    const copyTooltipText = ref('Copy to clipboard')
    const copyToClipboard = (text) => {
      $store.dispatch('showNotification', { message: 'copied to clipboard' })
      navigator.clipboard.writeText(text)
      copyTooltipText.value = 'Copied!'
      setTimeout(() => {
        copyTooltipText.value = 'Copy to clipboard'
      }, 500)
    }

    return {
      showBastionOptions,
      bastion,
      bastionId,
      httpEnabled,
      httpPort,
      httpsPort,
      sshEnabled,
      sshPort,
      sshAuthorizedKeys,
      copyTooltipText,
      copyToClipboard
    }
  }
}
</script>
