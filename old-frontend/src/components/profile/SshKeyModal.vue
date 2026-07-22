<template>
  <b-modal
    id="sshKeyModal"
    v-model="showSshKeyModal"
    size="lg"
    :title="$t('forms.ssh-key.modal.title')"
    centered
    header-class="bg-blue text-white"
    hide-footer
    @hidden="closeModal"
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <p>
          {{ $t('forms.ssh-key.modal.description') }}
        </p>
        <b-form-group
          :label="$t('forms.ssh-key.modal.label')"
          label-for="sshKeyInput"
        >
          <b-form-textarea
            id="sshKeyInput"
            v-model="sshKey"
            rows="3"
            no-resize
            :state="sshKey ? isValid : null"
            placeholder="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... user@host"
          />
          <b-form-invalid-feedback :state="sshKey ? isValid : null">
            {{ $t('forms.ssh-key.modal.invalid') }}
          </b-form-invalid-feedback>
        </b-form-group>
        <div class="w-100 d-flex justify-content-end">
          <b-button
            v-if="hasKey"
            variant="danger"
            class="mr-2"
            :title="$t('forms.ssh-key.modal.buttons.remove')"
            @click="submitRemove"
          >
            {{ $t('forms.ssh-key.modal.buttons.remove') }}
          </b-button>
          <b-button
            class="btn-blue"
            :disabled="!sshKey || !isValid"
            :title="$t('forms.ssh-key.modal.buttons.save')"
            @click="submitSave"
          >
            {{ $t('forms.ssh-key.modal.buttons.save') }}
          </b-button>
        </div>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'

// Mirrors the server-side validation in apiv4 `validate_ssh_public_key`:
// a single known key type followed by a base64 blob and an optional comment.
const SSH_KEY_RE = /^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/]+={0,3}(\s+\S.*)?$/

export default {
  setup (_, context) {
    const $store = context.root.$store
    const sshKey = ref('')

    const showSshKeyModal = computed({
      get: () => $store.getters.getShowSshKeyModal,
      set: (value) => $store.commit('setShowSshKeyModal', value)
    })
    const storedKey = computed(() => $store.getters.getUserBastionSshKey)
    const hasKey = computed(() => !!storedKey.value)

    watch(showSshKeyModal, (open) => {
      if (open) {
        sshKey.value = storedKey.value || ''
      }
    })

    const isValid = computed(() => SSH_KEY_RE.test((sshKey.value || '').trim()))

    const submitSave = async () => {
      const ok = await $store.dispatch('updateUserBastionSshKey', sshKey.value.trim())
      if (ok) {
        showSshKeyModal.value = false
      }
    }
    const submitRemove = async () => {
      const ok = await $store.dispatch('deleteUserBastionSshKey')
      if (ok) {
        sshKey.value = ''
        showSshKeyModal.value = false
      }
    }
    const closeModal = () => {
      showSshKeyModal.value = false
    }

    return {
      sshKey,
      showSshKeyModal,
      hasKey,
      isValid,
      submitSave,
      submitRemove,
      closeModal
    }
  }
}
</script>
