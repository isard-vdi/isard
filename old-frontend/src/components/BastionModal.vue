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
    <hr>
    <b-row
      v-if="modal.bastion.ssh.enabled"
      class="ml-2 pr-3"
    >
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
    <b-row
      v-if="modal.bastion.http.enabled"
      class="ml-2 pr-3"
    >
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

    const sshUrl = ref(`ssh ${modal.value.bastion.id}@${window.location.hostname} -p ${config.value.bastionSshPort}`)
    const httpUrl = ref(`http://${modal.value.bastion.id}.${window.location.hostname}`)
    const httpsUrl = ref(`https://${modal.value.bastion.id}.${window.location.hostname}`)
    watch(modal.value, (value) => {
      sshUrl.value = `ssh ${value.bastion.id}@${window.location.hostname} -p ${config.value.bastionSshPort}`
      httpUrl.value = `http://${value.bastion.id}.${window.location.hostname}${config.value.httpPort === '80' ? '' : `:${config.value.httpPort}`}`
      httpsUrl.value = `https://${value.bastion.id}.${window.location.hostname}${config.value.httpsPort === '443' ? '' : `:${config.value.httpsPort}`}`
    })

    const copyToClipboard = (text) => {
      navigator.clipboard.writeText(text)
      $store.dispatch('showNotification', { message: i18n.t('forms.domain.viewers.bastion.copied') })
    }

    return {
      modal,
      closeModal,
      sshUrl,
      httpUrl,
      httpsUrl,
      copyToClipboard
    }
  }
}
</script>
