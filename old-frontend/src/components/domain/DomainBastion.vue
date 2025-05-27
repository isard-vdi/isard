<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
      <strong>{{ $t('forms.domain.bastion.title') }}</strong>
    </h4>
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
          />{{ $t('forms.domain.bastion.disabled') }}</label>
          <b-form-checkbox
            id="checkbox-bastion"
            v-model="bastion"
            switch
          >
            <b-icon
              class="mr-2"
              icon="door-open"
              variant="success"
            />{{ $t('forms.domain.bastion.enabled') }}
          </b-form-checkbox>
        </div>
      </b-col>
    </b-row>
    <!-- Bastion Options -->
    <span
      v-if="showBastionOptions"
    >
      <div
        v-if="bastionId"
        class="d-flex align-items-start"
      >
        <h5
          v-b-tooltip="{ title: `${copyTooltipText}`,
                         placement: 'top',
                         customClass: 'isard-tooltip',
                         trigger: 'hover' }"
          class="cursor-pointer w-fit-content"
          @click="copyToClipboard(bastionId)"
        >
          <b>ID:</b> {{ bastionId }}
        </h5>
      </div>

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
            {{ $t('forms.domain.bastion.http.checkbox') }}
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
            <label for="httpPortField">
              {{ $t('forms.domain.bastion.http.http-port') }}
              <b-icon
                v-b-tooltip="{ title: $t('forms.domain.bastion.port-tooltip', { port: getConfig.httpPort }),
                               placement: 'top',
                               customClass: 'isard-tooltip isard-tooltip-lg',
                               trigger: 'hover' }"
                icon="info-circle"
              />
            </label>
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
            <label for="httpPortField">
              {{ $t('forms.domain.bastion.http.https-port') }}
              <b-icon
                v-b-tooltip="{ title: $t('forms.domain.bastion.port-tooltip', { port: getConfig.httpsPort }),
                               placement: 'top',
                               customClass: 'isard-tooltip isard-tooltip-lg',
                               trigger: 'hover' }"
                icon="info-circle"
              />
            </label>
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

        <b-row
          v-if="getConfig.canUseBastionIndividualDomains"
          class="mt-2"
        >
          <b-col
            cols="4"
            xl="2"
          >
            <label for="httpDomainNameField">
              {{ $t('forms.domain.bastion.http.domain-name') }}
              <b-icon
                id="tooltip-target-1"
                icon="info-circle"
              />
              <b-tooltip
                target="tooltip-target-1"
                placement="top"
                custom-class="isard-tooltip isard-tooltip-lg"
                triggers="hover"
              >
                {{ $t('views.desktop.bastion_modal.domain-info.cname') }}<br>
                <code class="bg-white p-1 rounded-sm">
                  {{ cnameTarget }}
                  <b-icon
                    v-b-tooltip="{ title: `${copyTooltipText}`,
                                   placement: 'top',
                                   customClass: 'isard-tooltip',
                                   trigger: 'hover' }"
                    icon="clipboard"
                    class="cursor-pointer"
                    @click="copyToClipboard(cnameTarget)"
                  />
                </code>
              </b-tooltip>
            </label>
          </b-col>
          <b-col
            cols="6"
            xl="4"
          >
            <b-form-input
              id="httpDomainNameField"
              v-model="customDomainName"
              type="text"
              size="sm"
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
            {{ $t('forms.domain.bastion.ssh.checkbox') }}
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
            <label for="sshPortField">
              {{ $t('forms.domain.bastion.ssh.port') }}
              <b-icon
                v-b-tooltip="{ title: $t('forms.domain.bastion.port-tooltip', { port: getConfig.httpsPort }),
                               placement: 'top',
                               customClass: 'isard-tooltip isard-tooltip-lg',
                               trigger: 'hover' }"
                icon="info-circle"
              />
            </label>
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
            >{{ $t('forms.domain.bastion.ssh.authorized-keys') }}</label>
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
import { mapGetters } from 'vuex'
import i18n from '@/i18n'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const bastionData = computed(() => $store.getters.getBastion)
    const config = computed(() => $store.getters.getConfig)

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
        context.emit('toggleBastion', true)
        showBastionOptions.value = true
      } else {
        context.emit('toggleBastion', false)
        showBastionOptions.value = false
      }
      if (!wireguard.value) {
        if (newVal) {
          showBastionOptions.value = true
          ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.bastion-wireguard-network-added'), '', true, 5000)
          domain.value.hardware.interfaces = [...domain.value.hardware.interfaces, 'wireguard']
          $store.commit('setDomain', domain.value)
        } else {
          showBastionOptions.value = false
        }
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
        bastionData.value.http.http_port = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const httpsPort = computed({
      get: () => $store.getters.getBastion.http.https_port,
      set: (value) => {
        bastionData.value.http.https_port = value
        $store.commit('setBastion', bastionData.value)
      }
    })
    const cnameTarget = computed(() => {
      return `${bastionId.value}.${config.value.bastionDomain}`
    })
    const customDomainName = computed({
      get: () => $store.getters.getBastion.domain || '',
      set: (value) => {
        bastionData.value.domain = value || null
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
    const copyTooltipText = ref(i18n.t('forms.domain.bastion.copy'))
    const copyToClipboard = (text) => {
      navigator.clipboard.writeText(text)
      copyTooltipText.value = i18n.t('forms.domain.bastion.copied')
      setTimeout(() => {
        copyTooltipText.value = i18n.t('forms.domain.bastion.copy')
      }, 750)
    }

    const domain = computed(() => $store.getters.getDomain)
    const wireguard = computed(() => domain.value.hardware.interfaces.includes('wireguard'))

    watch(wireguard, (newVal, prevVal) => {
      if (!wireguard.value) {
        ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.wireguard-bastion-removed'), '', true, 5000)
        bastion.value = false
      }
    })

    return {
      showBastionOptions,
      bastion,
      bastionId,
      httpEnabled,
      httpPort,
      httpsPort,
      cnameTarget,
      customDomainName,
      sshEnabled,
      sshPort,
      sshAuthorizedKeys,
      copyTooltipText,
      copyToClipboard
    }
  },
  computed: {
    ...mapGetters(['getConfig'])
  }
}
</script>
