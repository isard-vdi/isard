<template>
  <div class="modal-rdp text-center">
    <b-spinner v-if="loading" />
    <h2>{{ title[status] || i18n.t('components.rdp-modal.title.connecting') }}</h2>
    <p>{{ message || text[status] }}</p>
    <button
      v-if="!loading"
      class="buttonRefresh"
      @click="refreshRdpWindow"
    >
      {{ $t(retry === maxRetries ? 'components.rdp-modal.buttons.retry' : 'components.rdp-modal.buttons.refresh') }}
    </button>
  </div>
</template>
<script>
import states from '@/lib/states'
import i18n from '@/i18n'
import { computed } from '@vue/composition-api'

export default {
  props: {
    retry: {
      type: Number,
      default: 0
    },
    maxRetries: {
      type: Number,
      default: 0
    }
  },
  setup (props, context) {
    const title = computed(() => ({
      CONNECTED: i18n.t('components.rdp-modal.title.connecting'),
      CONNECTING: i18n.t('components.rdp-modal.title.connecting'),
      DISCONNECTED: i18n.t('components.rdp-modal.title.disconnected'),
      UNSTABLE: i18n.t('components.rdp-modal.title.unstable'),
      WAITING: i18n.t('components.rdp-modal.title.connecting'),
      CLIENT_ERROR: i18n.t('components.rdp-modal.title.error'),
      COOKIE_ERROR: i18n.t('components.rdp-modal.title.error'),
      VIEWER_TOKEN_ERROR: i18n.t('components.rdp-modal.title.error'),
      COOKIE_EXPIRED: i18n.t('components.rdp-modal.title.error'),
      RETRYING: i18n.t('components.rdp-modal.title.retrying'),
      RDP_NOT_RUNNING: i18n.t('components.rdp-modal.title.rdp-not-running')
    }))

    const text = computed(() => ({
      CONNECTED: i18n.t('components.rdp-modal.message.connecting'),
      CONNECTING: i18n.t('components.rdp-modal.message.connecting'),
      DISCONNECTED: i18n.t('components.rdp-modal.message.disconnected'),
      UNSTABLE: i18n.t('components.rdp-modal.message.unstable'),
      WAITING: i18n.t('components.rdp-modal.message.connecting'),
      CLIENT_ERROR: i18n.t('components.rdp-modal.message.error'),
      COOKIE_ERROR: i18n.t('components.rdp-modal.message.cookie-error'),
      VIEWER_TOKEN_ERROR: i18n.t('components.rdp-modal.message.viewer-token-error'),
      COOKIE_EXPIRED: i18n.t('components.rdp-modal.message.cookie-expired'),
      RETRYING: i18n.t('components.rdp-modal.message.retrying', { retry: props.retry, maxRetries: props.maxRetries }),
      RDP_NOT_RUNNING: i18n.t('components.rdp-modal.message.rdp-not-running')
    }))

    return {
      status: states.CONNECTING,
      message: i18n.t('components.rdp-modal.message.connecting'),
      title,
      text
    }
  },
  computed: {
    loading () {
      return this.status === states.CONNECTING || this.status === states.CONNECTED || this.status === states.WAITING || this.status === states.RETRYING
    }
  },
  methods: {
    show (state, message) {
      this.message = ''
      this.status = state
      if (message) this.message = message
    },
    refreshRdpWindow () {
      window.location.reload()
    }
  }
}
</script>
<style scoped>
.modal-rdp {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);

  border-radius: 5px;
  padding: 1rem;
}

.rct {
  text-decoration: underline;
  cursor: pointer;
}

.buttonRefresh {
  display: inline-block;
  padding: 0.3em 1.2em;
  margin:0 0.3em 0.3em 0;
  border-radius:2em;
  box-sizing: border-box;
  text-decoration:none;
  font-family:'Roboto',sans-serif;
  font-weight:300;
  color:#FFFFFF;
  background-color:#4eb5f1;
  text-align:center;
  transition: all 0.2s;
}

.buttonRefresh:hover {
  background-color:#4095c6;
}

@media all and (max-width:30em) {
  .buttonRefresh {
  display: block;
  margin: 0.2em auto;
  }
}
</style>
