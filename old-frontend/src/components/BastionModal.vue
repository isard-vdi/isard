<template>
  <b-modal
    id="recycleBinModal"
    v-model="modal.show"
    size="lg"
    :title="$t('views.desktop.bastion_modal.title', { name: modal.desktop.name })"
    centered
    hide-footer
    @hidden="closeModal"
  >
    <b-row
      class="ml-2 mt-2 pr-3"
    >
      <label
        for="bastionId"
        class="ml-2 mb-0"
      >
        {{ $t('views.desktop.bastion_modal.labels.id') }}
      </label>
      <b-input-group
        id="bastionId"
        class="mb-2"
      >
        <b-form-input
          readonly
          :value="modal.bastion.id"
        />
        <b-input-group-append>
          <b-button
            :title="$t('views.desktop.bastion_modal.titles.id_copy')"
            @click="copyToClipboard(modal.bastion.id)"
          >
            <b-icon
              icon="clipboard"
            />
          </b-button>
        </b-input-group-append>
      </b-input-group>
    </b-row>

    <template v-if="modal.bastion.http.enabled">
      <hr>
      <b-row class="ml-2 pr-3">
        <label
          for="bastionHttpUrl"
          class="ml-2 mb-0"
          :title="$t('views.desktop.bastion_modal.titles.http_port', { http_port: modal.bastion.http.http_port })"
        >
          {{ $t('views.desktop.bastion_modal.labels.http') }}
        </label>
        <b-input-group
          id="bastionHttpUrl"
          class="mb-3"
        >
          <b-form-input
            readonly
            :value="httpUrl"
          />
          <b-input-group-append>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.http_open')"
              :href="httpUrl"
              target="_blank"
            >
              <b-icon
                icon="box-arrow-up-right"
              />
            </b-button>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.http_copy')"
              @click="copyToClipboard(httpUrl)"
            >
              <b-icon
                icon="clipboard"
              />
            </b-button>
          </b-input-group-append>
        </b-input-group>

        <label
          for="bastionHttpsUrl"
          class="ml-2 mb-0"
          :title="$t('views.desktop.bastion_modal.titles.https_port', { https_port: modal.bastion.http.https_port })"
        >
          {{ $t('views.desktop.bastion_modal.labels.https') }}
        </label>
        <b-input-group
          id="bastionHttpUrl"
          class="mb-3"
        >
          <b-form-input
            readonly
            :value="httpsUrl"
          />
          <b-input-group-append>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.http_open')"
              :href="httpsUrl"
              target="_blank"
            >
              <b-icon
                icon="box-arrow-up-right"
              />
            </b-button>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.https_copy')"
              @click="copyToClipboard(httpsUrl)"
            >
              <b-icon
                icon="clipboard"
              />
            </b-button>
          </b-input-group-append>
        </b-input-group>
      </b-row>
      <b-row
        v-if="canChangeDomain"
        class="ml-2 pr-3"
      >
        <label
          for="sshAuthorizedKeysField"
          class="ml-2 mb-0"
        >
          {{ $t('views.desktop.bastion_modal.labels.domain-name') }}
        </label>
        <b-input-group
          id="bastionHttpUrl"
          class="mb-3"
        >
          <b-form-input
            v-model="DomainName"
          />
          <b-input-group-append>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.domain-info')"
              class="btn-blue"
              @click="showDNSInfo = !showDNSInfo"
            >
              <b-icon
                icon="info-circle-fill"
              />
            </b-button>
          </b-input-group-append>
        </b-input-group>
        <div
          v-if="showDNSInfo"
          class="w-100"
        >
          <b-alert
            show
            variant="info"
          >
            <b-icon
              class="mr-2"
              icon="info-circle-fill"
            />
            {{ $t('views.desktop.bastion_modal.domain-info.title') }}<br>
            <br>
            {{ $t('views.desktop.bastion_modal.domain-info.cname') }}
            <code>
              {{ cnameTarget }}
              <b-icon
                icon="clipboard"
                class="cursor-pointer"
                @click="copyToClipboard(cnameTarget)"
              />
            </code>
          </b-alert>
        </div>
        <div class="w-100">
          <b-button
            class="mt-2 btn-blue float-right"
            @click="updateHttpDomain"
          >
            {{ $t('views.desktop.bastion_modal.buttons.update-domain') }}
          </b-button>
        </div>
      </b-row>
    </template>

    <template v-if="modal.bastion.ssh.enabled">
      <hr>
      <b-row class="ml-2 pr-3">
        <label
          for="bastionSshUrl"
          class="ml-2 mb-0"
          :title="$t('views.desktop.bastion_modal.titles.ssh_port', { ssh_port: modal.bastion.ssh.port })"
        >
          {{ $t('views.desktop.bastion_modal.labels.ssh') }}
        </label>
        <b-input-group
          id="bastionSshUrl"
          class="mb-3"
        >
          <b-form-input
            readonly
            :value="sshUrl"
          />
          <b-input-group-append>
            <b-button
              :title="$t('views.desktop.bastion_modal.titles.ssh_copy')"
              @click="copyToClipboard(sshUrl)"
            >
              <b-icon
                icon="clipboard"
              />
            </b-button>
          </b-input-group-append>
        </b-input-group>
      </b-row>
      <b-row class="ml-2 pr-3">
        <label
          for="sshAuthorizedKeysField"
          class="ml-2 mb-0"
          :title="$t('views.desktop.bastion_modal.titles.authorized-keys-ssh')"
        >
          {{ $t('views.desktop.bastion_modal.labels.authorized-keys-ssh') }}
        </label>
        <b-form-textarea
          id="sshAuthorizedKeysField"
          v-model="sshAuthorizedKeys"
          size="sm"
          rows="3"
          no-resize
          placeholder="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7..."
        />
        <div class="w-100">
          <b-button
            class="mt-2 btn-blue float-right"
            @click="updateSshAuthorizedKeys"
          >
            {{ $t('views.desktop.bastion_modal.buttons.update-authorized-keys') }}
          </b-button>
        </div>
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
    const config = computed(() => $store.getters.getConfig)

    const modal = computed(() => $store.getters.getBastionModal)

    const closeModal = () => {
      $store.dispatch('bastionModalShow', { show: false })
    }

    const targetIdSplit = computed(() => {
      // return the id with the last `-` replaced by `.`
      if (!modal.value?.bastion?.id) return ''
      return modal.value?.bastion?.id.split('-').slice(0, -1).join('-') + '.' + modal.value.bastion.id.split('-').slice(-1)[0]
    })

    const httpUrl = computed(() => {
      const port = config.value.httpPort === '80' ? '' : `:${config.value.httpPort}`
      if (modal.value.bastion.domain) {
        return `http://${modal.value.bastion.domain}${port}`
      }
      return `http://${targetIdSplit.value}.${modal.value.bastion.domain || config.value.bastionDomain || window.location.hostname}${port}`
    })
    const httpsUrl = computed(() => {
      const port = config.value.httpsPort === '443' ? '' : `:${config.value.httpsPort}`
      if (modal.value.bastion.domain) {
        return `https://${modal.value.bastion.domain}${port}`
      }
      return `https://${targetIdSplit.value}.${config.value.bastionDomain || window.location.hostname}${port}`
    })
    const sshUrl = computed(() => {
      const port = config.value.bastionSshPort === '22' ? '' : ` -p ${config.value.bastionSshPort}`
      return `ssh ${modal.value.bastion.id}@${config.value.bastionDomain || window.location.hostname}${port}`
    })

    const copyToClipboard = (text) => {
      navigator.clipboard.writeText(text)
      $store.dispatch('showNotification', { message: i18n.t('forms.domain.bastion.copied') })
    }

    const splitNewLine = (text) => text.split(/\r?\n/)
    const joinNewLine = (array) => array.join('\n')

    const sshAuthorizedKeys = computed({
      get: () => joinNewLine($store.getters.getBastionModal.bastion.ssh.authorized_keys),
      set: (value) => {
        modal.value.bastion.ssh.authorized_keys = splitNewLine(value)
        $store.commit('setBastion', modal.value)
      }
    })

    const updateSshAuthorizedKeys = () => {
      $store.dispatch('updateBastionAuthorizedKeys', modal.value.bastion)
    }

    const DomainName = ref(modal.value.bastion.domain || '')
    watch(() => modal.value.bastion.domain, (newValue) => {
      DomainName.value = newValue || ''
    })

    const showDNSInfo = ref(false)
    const cnameTarget = computed(() => {
      return `${modal.value.bastion.id}.${config.value.bastionDomain}`
    })

    const updateHttpDomain = () => {
      const data = {
        ...modal.value.bastion,
        domain: DomainName.value
      }

      $store.dispatch('updateBastionDomainName', data)
    }

    const canChangeDomain = computed(() => {
      return config.value.canUseBastionIndividualDomains
    })

    return {
      modal,
      closeModal,
      sshUrl,
      httpUrl,
      httpsUrl,
      copyToClipboard,
      sshAuthorizedKeys,
      joinNewLine,
      updateSshAuthorizedKeys,
      DomainName,
      showDNSInfo,
      cnameTarget,
      updateHttpDomain,
      canChangeDomain
    }
  }
}
</script>
