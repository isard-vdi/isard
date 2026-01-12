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
          class="ml-2 mb-0"
        >
          {{ $t('views.desktop.bastion_modal.labels.domain-names') }}
          <b-badge variant="info">{{ domainNames.length }}/10</b-badge>
          <b-button
            variant="link"
            size="sm"
            :title="$t('views.desktop.bastion_modal.titles.domain-info')"
            @click="showDNSInfo = !showDNSInfo"
          >
            <b-icon
              icon="info-circle-fill"
            />
          </b-button>
        </label>
        <div
          v-if="showDNSInfo"
          class="w-100 mb-2"
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
        <div
          v-for="(domain, index) in domainNames"
          :key="index"
          class="w-100 mb-2"
        >
          <b-input-group>
            <b-input-group-prepend>
              <b-input-group-text
                v-if="isDomainSaved(domain)"
                v-b-tooltip.hover
                :title="$t('views.desktop.bastion_modal.domain-status.verified')"
                class="bg-success text-white"
              >
                <b-icon icon="check-circle-fill" />
              </b-input-group-text>
              <b-input-group-text
                v-else-if="getDomainStatus(index) === 'verified'"
                v-b-tooltip.hover
                :title="$t('views.desktop.bastion_modal.domain-status.verified-pending-save')"
                class="bg-info text-white"
              >
                <b-icon icon="check-circle" />
              </b-input-group-text>
              <b-input-group-text
                v-else-if="getDomainStatus(index) === 'verifying'"
                class="bg-secondary text-white"
              >
                <b-spinner small />
              </b-input-group-text>
              <b-input-group-text
                v-else
                v-b-tooltip.hover
                :title="$t('views.desktop.bastion_modal.domain-status.not-verified')"
                class="bg-warning text-dark"
              >
                <b-icon icon="exclamation-circle-fill" />
              </b-input-group-text>
            </b-input-group-prepend>
            <b-form-input
              :value="domain"
              @input="updateDomainAtIndex(index, $event)"
            />
            <b-input-group-append>
              <b-button
                v-if="!isDomainSaved(domain) && getDomainStatus(index) !== 'verified' && getDomainStatus(index) !== 'verifying'"
                variant="outline-primary"
                :title="$t('views.desktop.bastion_modal.buttons.verify-domain')"
                @click="verifyDomain(index)"
              >
                <b-icon icon="shield-check" />
              </b-button>
              <b-button
                variant="outline-danger"
                @click="removeDomainAtIndex(index)"
              >
                <b-icon icon="trash" />
              </b-button>
            </b-input-group-append>
          </b-input-group>
        </div>
        <div
          v-if="domainNames.length < 10"
          class="w-100 mb-2"
        >
          <b-button
            variant="outline-primary"
            size="sm"
            @click="addDomain"
          >
            <b-icon icon="plus" /> {{ $t('views.desktop.bastion_modal.buttons.add-domain') }}
          </b-button>
        </div>
        <div class="w-100">
          <b-button
            class="mt-2 btn-blue float-right"
            @click="updateHttpDomains"
          >
            {{ $t('views.desktop.bastion_modal.buttons.update-domains') }}
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

    const firstDomain = computed(() => {
      const domains = modal.value.bastion.domains || []
      return domains.length > 0 ? domains[0] : null
    })
    const httpUrl = computed(() => {
      const port = config.value.httpPort === '80' ? '' : `:${config.value.httpPort}`
      if (firstDomain.value) {
        return `http://${firstDomain.value}${port}`
      }
      return `http://${targetIdSplit.value}.${config.value.bastionDomain || window.location.hostname}${port}`
    })
    const httpsUrl = computed(() => {
      const port = config.value.httpsPort === '443' ? '' : `:${config.value.httpsPort}`
      if (firstDomain.value) {
        return `https://${firstDomain.value}${port}`
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

    // Track saved domains (from server) and local domain list
    const savedDomains = ref(new Set(modal.value.bastion.domains || []))
    const domainNames = ref([...(modal.value.bastion.domains || [])])
    // Track verification status per index: 'pending', 'verifying', 'verified', 'failed'
    const domainStatuses = ref({})

    watch(() => modal.value.bastion.domains, (newValue) => {
      savedDomains.value = new Set(newValue || [])
      domainNames.value = [...(newValue || [])]
      domainStatuses.value = {}
    })

    const isDomainSaved = (domain) => {
      return domain && savedDomains.value.has(domain)
    }

    const getDomainStatus = (index) => {
      return domainStatuses.value[index] || 'pending'
    }

    const addDomain = () => {
      if (domainNames.value.length < 10) {
        domainNames.value = [...domainNames.value, '']
      }
    }
    const removeDomainAtIndex = (index) => {
      domainNames.value = domainNames.value.filter((_, i) => i !== index)
      // Rebuild statuses with shifted indexes
      const newStatuses = {}
      Object.keys(domainStatuses.value).forEach(key => {
        const keyNum = parseInt(key)
        if (keyNum < index) {
          newStatuses[keyNum] = domainStatuses.value[keyNum]
        } else if (keyNum > index) {
          newStatuses[keyNum - 1] = domainStatuses.value[keyNum]
        }
      })
      domainStatuses.value = newStatuses
    }
    const updateDomainAtIndex = (index, value) => {
      const newDomains = [...domainNames.value]
      newDomains[index] = value
      domainNames.value = newDomains
      // Reset verification status when domain changes
      if (domainStatuses.value[index]) {
        const newStatuses = { ...domainStatuses.value }
        delete newStatuses[index]
        domainStatuses.value = newStatuses
      }
    }

    const verifyDomain = async (index) => {
      const domain = domainNames.value[index]
      if (!domain || !domain.trim()) return

      domainStatuses.value = { ...domainStatuses.value, [index]: 'verifying' }

      const result = await $store.dispatch('verifyBastionDomain', {
        desktop_id: modal.value.desktop.id,
        domain: domain.trim()
      })

      if (result.success) {
        domainStatuses.value = { ...domainStatuses.value, [index]: 'verified' }
        $store.dispatch('showNotification', { message: i18n.t('messages.info.bastion-domain-verified') })
      } else {
        domainStatuses.value = { ...domainStatuses.value, [index]: 'failed' }
      }
    }

    const showDNSInfo = ref(false)
    const cnameTarget = computed(() => {
      return `${modal.value.bastion.id}.${config.value.bastionDomain}`
    })

    const updateHttpDomains = () => {
      const data = {
        desktop_id: modal.value.desktop.id,
        domains: domainNames.value.filter(d => d)
      }

      $store.dispatch('updateBastionDomains', data)
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
      domainNames,
      addDomain,
      removeDomainAtIndex,
      updateDomainAtIndex,
      isDomainSaved,
      getDomainStatus,
      verifyDomain,
      showDNSInfo,
      cnameTarget,
      updateHttpDomains,
      canChangeDomain
    }
  }
}
</script>
