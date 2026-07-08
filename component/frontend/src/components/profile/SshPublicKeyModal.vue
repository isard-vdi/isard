<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import Modal from '@/components/modal/Modal.vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import {
  getUserBastionSshKeyOptions,
  setUserBastionSshKeyMutation,
  deleteUserBastionSshKeyMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t } = useI18n()

// Mirrors the server-side validation in apiv4 `validate_ssh_public_key`:
// a single known key type followed by a base64 blob and an optional comment.
const SSH_KEY_RE =
  /^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/]+={0,3}(\s+\S.*)?$/

// The optional trailing comment in SSH_KEY_RE is greedy enough to swallow a
// second key pasted on the same line ("ssh-ed25519 AAA... ssh-ed25519 BBB..."),
// so it would validate as one key with a comment. This modal only accepts a
// SINGLE key, so also require exactly one key-type token in the input.
const SSH_KEY_TYPE_RE =
  /(?:^|\s)(?:ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(?:256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s/g

const countKeyTypes = (value: string) => (` ${value} `.match(SSH_KEY_TYPE_RE) || []).length

const keyInput = ref<string>('')
const errorMessage = ref<string>('')

const { data: sshKeyData, refetch: refetchSshKey } = useQuery({
  ...getUserBastionSshKeyOptions(),
  enabled: computed(() => props.open)
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      keyInput.value = sshKeyData.value?.ssh_key || ''
      errorMessage.value = ''
    }
  }
)
watch(
  () => sshKeyData.value,
  (data) => {
    if (props.open) keyInput.value = data?.ssh_key || ''
  }
)

const storedKey = computed(() => sshKeyData.value?.ssh_key || '')
const hasKey = computed(() => storedKey.value.trim().length > 0)
const isValid = computed(() => {
  const trimmed = keyInput.value.trim()
  return SSH_KEY_RE.test(trimmed) && countKeyTypes(trimmed) === 1
})

const { mutateAsync: setSshKey, isPending: isSaving } = useMutation(setUserBastionSshKeyMutation())
const { mutateAsync: deleteSshKey, isPending: isDeleting } = useMutation(
  deleteUserBastionSshKeyMutation()
)

const isActionDisabled = computed(() => isSaving.value || isDeleting.value)

const handleClose = () => {
  emit('update:open', false)
}

const handleSave = async () => {
  errorMessage.value = ''
  try {
    await setSshKey({ body: { ssh_key: keyInput.value.trim() } })
    await refetchSshKey()
    emit('update:open', false)
  } catch {
    errorMessage.value = t('components.profile.ssh-key-modal.alert.error-save')
  }
}

const handleRemove = async () => {
  errorMessage.value = ''
  try {
    await deleteSshKey({})
    keyInput.value = ''
    await refetchSshKey()
    emit('update:open', false)
  } catch {
    errorMessage.value = t('components.profile.ssh-key-modal.alert.error-remove')
  }
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.profile.ssh-key-modal.title')"
    size="3xl"
    :close-on-backdrop-click="true"
    @close="handleClose"
  >
    <div class="flex flex-col px-2 gap-6">
      <Alert
        v-if="errorMessage"
        variant="destructive"
        class="border-error-200 flex items-start gap-3"
      >
        <FeaturedIconOutline kind="outline" color="error" size="md" class="shrink-0" />
        <div class="space-y-1 text-left">
          <AlertTitle class="text-error-900">
            {{ t('components.profile.ssh-key-modal.alert.error-title') }}
          </AlertTitle>
          <AlertDescription class="text-error-700">
            {{ errorMessage }}
          </AlertDescription>
        </div>
      </Alert>

      <p class="text-sm text-gray-warm-700">
        {{ t('components.profile.ssh-key-modal.description') }}
      </p>

      <Alert class="border-warning-200 flex items-start gap-3">
        <FeaturedIconOutline kind="outline" color="warning" size="md" class="shrink-0" />
        <div class="space-y-1 text-left">
          <AlertDescription class="text-gray-warm-700">
            {{ t('components.profile.ssh-key-modal.security-note') }}
          </AlertDescription>
        </div>
      </Alert>

      <div class="space-y-2">
        <Textarea
          v-model="keyInput"
          class="bg-base-white h-28 font-mono text-sm whitespace-pre"
          :placeholder="t('components.profile.ssh-key-modal.placeholder')"
        />
        <p v-if="keyInput.trim() && !isValid" class="text-sm text-error-700">
          {{ t('components.profile.ssh-key-modal.invalid') }}
        </p>
      </div>
    </div>

    <template #footer>
      <div class="w-full flex justify-center gap-2 px-6">
        <Button
          v-if="hasKey"
          hierarchy="destructive"
          size="md"
          :disabled="isActionDisabled"
          @click="handleRemove"
        >
          {{ t('components.profile.ssh-key-modal.buttons.remove') }}
        </Button>
        <Button
          hierarchy="primary"
          size="md"
          :disabled="isActionDisabled || !keyInput.trim() || !isValid"
          @click="handleSave"
        >
          {{ t('components.profile.ssh-key-modal.buttons.save') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
