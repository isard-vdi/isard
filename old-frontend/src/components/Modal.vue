<template>
  <div class="modal-rdp">
    <b-spinner v-if="loading" />
    <h2>{{ title[status] || i18n.t('components.rdp-modal.title.connecting') }}</h2>
    <p>{{ message || text[status] }}</p>
    <button
      v-if="!loading"
      class="buttonRefresh"
      @click="refreshRdpWindow"
    >
      <i18n path="components.rdp-modal.button-refresh" />
    </button>
  </div>
</template>
<script>
import states from '@/lib/states'
import i18n from '@/i18n'

export default {
  data () {
    return {
      status: states.CONNECTING,
      message: i18n.t('components.rdp-modal.message.connecting'),
      title: {
        CONNECTED: i18n.t('components.rdp-modal.title.connecting'),
        CONNECTING: i18n.t('components.rdp-modal.title.connecting'),
        DISCONNECTED: i18n.t('components.rdp-modal.title.disconnected'),
        UNSTABLE: i18n.t('components.rdp-modal.title.unstable'),
        WAITING: i18n.t('components.rdp-modal.title.connecting'),
        CLIENT_ERROR: i18n.t('components.rdp-modal.title.error'),
        COOKIE_ERROR: i18n.t('components.rdp-modal.title.error'),
        COOKIE_EXPIRED: i18n.t('components.rdp-modal.title.error')
      },
      text: {
        CONNECTED: i18n.t('components.rdp-modal.message.connecting'),
        CONNECTING: i18n.t('components.rdp-modal.message.connecting'),
        DISCONNECTED: i18n.t('components.rdp-modal.message.disconnected'),
        UNSTABLE: i18n.t('components.rdp-modal.message.unstable'),
        WAITING: i18n.t('components.rdp-modal.message.connecting'),
        CLIENT_ERROR: i18n.t('components.rdp-modal.message.error'),
        COOKIE_ERROR: i18n.t('components.rdp-modal.message.cookie-error'),
        COOKIE_EXPIRED: i18n.t('components.rdp-modal.message.cookie-expired')
      }
    }
  },
  computed: {
    loading () {
      return this.status === states.CONNECTING || this.status === states.CONNECTED || this.status === states.WAITING
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
