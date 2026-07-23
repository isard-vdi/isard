<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'

import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'

import {
  getUserConfigOptions,
  getDesktopBastionLegacyOptions,
  getUserBastionSshKeyOptions,
  updateDesktopBastionAuthorizedKeysMutation,
  updateDesktopBastionDomainMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { BastionDirectViewerResponse } from '@/gen/oas/apiv4'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Code } from '@/components/code'
import { Icon, CopyIcon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Label } from '@/components/ui/label'
import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopId: string
  desktopName: string
  // Direct viewer: access info comes ready-made from get-details, because that
  // view can read neither the config nor the target. Switches to read-only.
  bastion?: BastionDirectViewerResponse
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  bastion: undefined
})

const emit = defineEmits<{
  close: []
}>()

const isReadOnly = computed(() => !!props.bastion)
const isEditable = computed(() => !isReadOnly.value)

// Every query below needs a logged-in user, so they only run when editable.
const {
  data: userConfig,
  isPending: userConfigIsPending,
  isError: userConfigIsError,
  error: userConfigError
} = useQuery({ ...getUserConfigOptions(), enabled: isEditable })

const {
  data: bastionTargetData,
  isPending: bastionTargetDataIsPending,
  isError: bastionTargetDataIsError,
  error: bastionTargetDataError,
  refetch: refetchBastionTargetData
} = useQuery({
  ...getDesktopBastionLegacyOptions({
    path: {
      desktop_id: props.desktopId
    }
  }),
  enabled: isEditable
})

const {
  mutate: saveBastionHttpDomain,
  mutateAsync: saveBastionHttpDomainAsync,
  isPending: saveBastionHttpDomainIsPending,
  isError: saveBastionHttpDomainIsError,
  error: saveBastionHttpDomainError
} = useMutation({
  ...updateDesktopBastionDomainMutation(),
  onSuccess: () => {
    refetchBastionTargetData()
  }
})

const {
  mutateAsync: saveBastionSshAuthorizedKeysAsync,
  isPending: saveBastionSshAuthorizedKeysIsPending
} = useMutation({
  ...updateDesktopBastionAuthorizedKeysMutation(),
  onSuccess: () => {
    refetchBastionTargetData()
  }
})

// The user's own profile key is managed automatically (injected at desktop
// start, kept first in the target). This box is only for OTHER people's keys,
// so we hide the user's own key here; on save the server re-prepends the owner
// key and strips the editor's own key.
const { data: userBastionSshKey } = useQuery({
  ...getUserBastionSshKeyOptions(),
  enabled: isEditable
})
const ownKey = computed(() => (userBastionSshKey.value?.ssh_key || '').trim())
const hasOwnKey = computed(() => ownKey.value.length > 0)

const bastionDomain = ref<string>('')
const bastionAuthorizedKeys = ref<string>('')
watch(
  [() => bastionTargetData.value, ownKey],
  ([newVal]) => {
    // TODO: migrate to the multi-domain (domains array) UI. For now we only
    // read/write the first custom domain.
    bastionDomain.value = newVal?.domains?.[0] || ''
    const own = ownKey.value
    const keys = (newVal?.ssh.authorized_keys || []).filter(
      (k): k is string => !!k && k.trim().length > 0 && k.trim() !== own
    )
    bastionAuthorizedKeys.value = keys.join('\n')
  },
  { immediate: true }
)

const bastionModalDnsAlertOpen = ref(false)

const hasTarget = computed(() =>
  isReadOnly.value ? !!props.bastion?.enabled : !!bastionTargetData.value
)
const targetId = computed(() =>
  isReadOnly.value ? (props.bastion?.id ?? '') : (bastionTargetData.value?.id ?? '')
)
const customDomains = computed(() =>
  isReadOnly.value
    ? (props.bastion?.custom_domains ?? [])
    : (bastionTargetData.value?.domains ?? [])
)
const httpEnabled = computed(() =>
  isReadOnly.value ? !!props.bastion?.http_enabled : !!bastionTargetData.value?.http.enabled
)
const sshEnabled = computed(() =>
  isReadOnly.value ? !!props.bastion?.ssh_enabled : !!bastionTargetData.value?.ssh.enabled
)

const targetIdSplit = computed(() => {
  // return the id with the last `-` replaced by `.`
  if (!bastionTargetData.value?.id) return ''
  return (
    bastionTargetData.value?.id.split('-').slice(0, -1).join('-') +
    '.' +
    bastionTargetData.value?.id.split('-').slice(-1)[0]
  )
})

// TODO: migrate to the multi-domain (domains array) UI. For now we only
// surface the first custom domain.
const httpUrl = computed(() => {
  if (isReadOnly.value) return props.bastion?.http_url ?? ''
  const port = userConfig.value?.http_port === '80' ? '' : `:${userConfig.value?.http_port}`
  if (bastionTargetData.value?.domains?.[0]) {
    return `http://${bastionTargetData.value?.domains?.[0]}${port}`
  }
  return `http://${targetIdSplit.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})
const httpsUrl = computed(() => {
  if (isReadOnly.value) return props.bastion?.https_url ?? ''
  const port = userConfig.value?.https_port === '443' ? '' : `:${userConfig.value?.https_port}`
  if (bastionTargetData.value?.domains?.[0]) {
    return `https://${bastionTargetData.value.domains[0]}${port}`
  }
  return `https://${targetIdSplit.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})
const sshUrl = computed(() => {
  if (isReadOnly.value) return props.bastion?.ssh_command ?? ''
  const port =
    userConfig.value?.bastion_ssh_port === '22' ? '' : ` -p ${userConfig.value?.bastion_ssh_port}`
  return `ssh ${bastionTargetData.value?.id}@${bastionTargetData.value?.domains?.[0] || userConfig.value?.bastion_domain || window.location.hostname}${port}`
})

const closeModal = () => {
  bastionModalDnsAlertOpen.value = false
  bastionDomain.value = ''
  bastionAuthorizedKeys.value = ''
  emit('close')
}

// A disabled query stays pending forever, so these states only apply when the
// data actually comes from a query.
const isPending = computed(
  () => isEditable.value && (userConfigIsPending.value || bastionTargetDataIsPending.value)
)
const isError = computed(
  () => isEditable.value && (userConfigIsError.value || bastionTargetDataIsError.value)
)

const domainNameForm = useForm({
  defaultValues: reactive({
    domainName: computed(() => bastionDomain.value)
  }),
  onSubmit: async ({ value }) => {
    await saveBastionHttpDomainAsync({
      body: {
        domain_name: value.domainName
      },
      path: {
        desktop_id: props.desktopId
      }
    })
  }
})

const authorizedKeysForm = useForm({
  defaultValues: reactive({
    authorizedKeys: computed(() => bastionAuthorizedKeys.value)
  }),
  onSubmit: async ({ value }) => {
    await saveBastionSshAuthorizedKeysAsync({
      body: {
        authorized_keys: value.authorizedKeys.split('\n').filter((k) => k.trim().length > 0)
      },
      path: {
        desktop_id: props.desktopId
      }
    })
  }
})
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    size="2xl"
    class="pt-6"
    :title="t('components.bastion-info-modal.title', { name: props.desktopName })"
    :description="
      t(
        isReadOnly
          ? 'components.bastion-info-modal.description-read-only'
          : 'components.bastion-info-modal.description'
      )
    "
    @close="closeModal"
  >
    <div class="flex flex-col gap-4 pb-4">
      <!-- Loading state -->
      <div
        v-if="isPending"
        class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
      >
        <Skeleton class="h-6 w-48" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-9 w-3/4" />
      </div>

      <!-- Error state -->
      <Alert v-else-if="isError" variant="destructive">
        <Icon name="alert-circle" stroke-color="error-700" />
        <AlertTitle>{{ t('components.bastion-info-modal.error.title') }}</AlertTitle>
        <AlertDescription>
          <p v-if="userConfigIsError">
            {{ t('components.bastion-info-modal.error-loading-user-config') }}:
            {{ userConfigError?.message || 'Unknown error' }}
          </p>
          <p v-if="bastionTargetDataIsError">
            {{ t('components.bastion-info-modal.error-loading-bastion-data') }}:
            {{ bastionTargetDataError?.message || 'Unknown error' }}
          </p>
        </AlertDescription>
      </Alert>

      <!-- Empty state: no bastion target -->
      <div
        v-else-if="!hasTarget"
        class="bg-base-white p-6 rounded-lg border border-gray-warm-300 flex flex-col items-center text-center gap-2"
      >
        <Icon name="globe-04" size="lg" stroke-color="gray-warm-400" />
        <p class="font-semibold text-gray-warm-700">
          {{ t('components.bastion-info-modal.no-bastion-configured') }}
        </p>
        <p class="text-sm text-gray-warm-600">
          {{ t('components.bastion-info-modal.no-bastion-configured-description') }}
        </p>
      </div>

      <template v-else>
        <!-- Target ID -->
        <section class="bg-base-white p-5 rounded-lg border border-gray-warm-300">
          <div class="flex items-center gap-2 mb-3">
            <Icon name="passcode" size="md" stroke-color="gray-warm-700" />
            <h3 class="font-semibold text-gray-warm-700">
              {{ t('components.bastion-info-modal.fields.target-id.title') }}
            </h3>
          </div>
          <div class="flex items-center gap-3">
            <code
              class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono truncate"
            >
              {{ targetId }}
            </code>
            <CopyIcon :value="targetId" stroke-color="gray-warm-600" />
          </div>
        </section>

        <!-- HTTP / HTTPS section -->
        <section
          v-if="httpEnabled"
          class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-4"
        >
          <div class="flex items-center gap-2">
            <Icon name="globe-04" size="md" stroke-color="gray-warm-700" />
            <h3 class="font-semibold text-gray-warm-700">
              {{ t('components.domain.access.bastion.http-https.label') }}
            </h3>
          </div>

          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-3">
              <code
                class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono truncate"
              >
                {{ httpUrl }}
              </code>
              <a :href="httpUrl" target="_blank" :title="httpUrl">
                <Icon
                  class="select-none cursor-pointer"
                  name="link-external-01"
                  size="md"
                  stroke-color="gray-warm-600"
                />
              </a>
              <CopyIcon :value="httpUrl" stroke-color="gray-warm-600" />
            </div>
            <div class="flex items-center gap-3">
              <code
                class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono truncate"
              >
                {{ httpsUrl }}
              </code>
              <a :href="httpsUrl" target="_blank" :title="httpsUrl">
                <Icon
                  class="select-none cursor-pointer"
                  name="link-external-01"
                  size="md"
                  stroke-color="gray-warm-600"
                />
              </a>
              <CopyIcon :value="httpsUrl" stroke-color="gray-warm-600" />
            </div>
          </div>

          <!-- All configured custom domains; the URLs above only use the first. -->
          <div
            v-if="customDomains.length"
            class="flex flex-col gap-2 pt-2 border-t border-gray-warm-200"
          >
            <Label class="text-sm text-gray-warm-700">
              {{ t('components.domain.access.bastion.custom-domains.label') }}
            </Label>
            <div class="flex flex-wrap gap-2">
              <code
                v-for="domain in customDomains"
                :key="domain"
                class="bg-gray-warm-50 border border-gray-warm-200 rounded px-2.5 py-1 text-sm font-mono"
              >
                {{ domain }}
              </code>
            </div>
          </div>

          <!-- Custom domain editor -->
          <div v-if="isEditable" class="flex flex-col gap-2 pt-2 border-t border-gray-warm-200">
            <Label class="text-sm text-gray-warm-700">
              {{ t('components.domain.access.bastion.http-https.custom-domains.label') }}
            </Label>
            <form
              class="flex items-center gap-2"
              @submit.prevent.stop="domainNameForm.handleSubmit"
            >
              <domainNameForm.Field v-slot="{ field }" name="domainName">
                <InputField
                  :id="field.name"
                  class="flex-1"
                  :placeholder="
                    t('components.domain.access.bastion.http-https.custom-domains.placeholder')
                  "
                  :name="field.name"
                  :model-value="field.state.value"
                  @blur="field.handleBlur"
                  @input="field.handleChange($event.target.value)"
                />
              </domainNameForm.Field>
              <Button
                hierarchy="primary"
                icon="save-02"
                :disabled="saveBastionHttpDomainIsPending"
                type="submit"
              />
            </form>
            <Label
              class="cursor-pointer flex items-center gap-1 text-sm text-gray-warm-600 hover:text-gray-warm-800"
              @click="bastionModalDnsAlertOpen = !bastionModalDnsAlertOpen"
            >
              {{
                bastionModalDnsAlertOpen
                  ? t('components.domain.access.bastion.http-https.custom-domains.less-details')
                  : t('components.domain.access.bastion.http-https.custom-domains.more-details')
              }}
              <Icon
                :name="bastionModalDnsAlertOpen ? 'chevron-up' : 'chevron-down'"
                size="sm"
                stroke-color="gray-warm-600"
              />
            </Label>
            <Alert v-if="bastionModalDnsAlertOpen" class="bg-gray-warm-50 border-gray-warm-300">
              <AlertTitle class="font-semibold text-gray-warm-700 mb-1">
                {{ t('components.domain.access.bastion.http-https.custom-domains.alert.title') }}
              </AlertTitle>
              <i18n-t
                keypath="components.domain.access.bastion.http-https.custom-domains.alert.description"
                tag="AlertDescription"
                class="text-gray-warm-700"
              >
                <template #cname-url>
                  <Code>{{
                    `${bastionTargetData!.desktop_id}.${userConfig?.bastion_domain}`
                  }}</Code>
                  <span class="inline-block mx-1">
                    <CopyIcon
                      class="inline-block"
                      :value="`${bastionTargetData!.desktop_id}.${userConfig?.bastion_domain}`"
                      size="sm"
                      stroke-color="gray-warm-600"
                    />
                  </span>
                </template>
              </i18n-t>
            </Alert>
          </div>
        </section>

        <!-- SSH section -->
        <section
          v-if="sshEnabled"
          class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-4"
        >
          <div class="flex items-center gap-2">
            <Icon name="terminal-square" size="md" stroke-color="gray-warm-700" />
            <h3 class="font-semibold text-gray-warm-700">
              {{ t('components.domain.access.bastion.ssh.label') }}
            </h3>
          </div>

          <div class="flex items-center gap-3">
            <code
              class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono truncate"
            >
              {{ sshUrl }}
            </code>
            <CopyIcon :value="sshUrl" stroke-color="gray-warm-600" />
          </div>

          <div v-if="isEditable" class="flex flex-col gap-2 pt-2 border-t border-gray-warm-200">
            <Label class="text-sm text-gray-warm-700">
              {{ t('components.domain.access.bastion.ssh.authorized-keys.others-label') }}
            </Label>
            <Alert v-if="!hasOwnKey" class="bg-gray-warm-50 border-gray-warm-300">
              <Icon name="alert-circle" size="sm" stroke-color="gray-warm-600" />
              <AlertDescription class="text-gray-warm-700">
                {{ t('components.domain.access.bastion.ssh.authorized-keys.own-key.missing') }}
                <RouterLink :to="{ name: 'profile' }" class="underline">
                  {{ t('components.domain.access.bastion.ssh.authorized-keys.own-key.add-link') }}
                </RouterLink>
              </AlertDescription>
            </Alert>
            <p v-else class="text-xs text-gray-warm-500">
              {{ t('components.domain.access.bastion.ssh.authorized-keys.own-key.managed') }}
            </p>
            <form
              class="flex items-start gap-2"
              @submit.prevent.stop="authorizedKeysForm.handleSubmit"
            >
              <authorizedKeysForm.Field v-slot="{ field }" name="authorizedKeys">
                <Textarea
                  :id="field.name"
                  class="flex-1 bg-base-white h-32 font-mono text-sm whitespace-pre"
                  :placeholder="
                    t('components.domain.access.bastion.ssh.authorized-keys.placeholder')
                  "
                  :name="field.name"
                  :model-value="field.state.value"
                  @blur="field.handleBlur"
                  @input="field.handleChange($event.target.value)"
                />
              </authorizedKeysForm.Field>
              <Button
                hierarchy="primary"
                icon="save-02"
                :disabled="saveBastionSshAuthorizedKeysIsPending"
                type="submit"
              />
            </form>
          </div>
        </section>
      </template>
    </div>
  </Modal>
</template>
