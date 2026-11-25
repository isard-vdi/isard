<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'

import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'
import { z } from 'zod'

import {
  getUserConfigOptions,
  getDesktopBastionLegacyOptions,
  getUserBastionSshKeyOptions,
  updateBastionDomainsMutation,
  updateDesktopBastionAuthorizedKeysMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { BastionDirectViewerResponse } from '@/gen/oas/apiv4'
import { toast } from '@/components/ui/toast'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Icon, CopyIcon } from '@/components/icon'
import { Label } from '@/components/ui/label'
import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { TruncatedText } from '@/components/truncated-text'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { RouterLink } from 'vue-router'
import BastionDomainsEditor from '@/components/domain/BastionDomainsEditor.vue'
import { describeApiError } from '@/lib/api-errors'
import { cleanDomains, domainsChanged, domainsOverLimit } from '@/lib/bastionDomains'
import { invalidAuthorizedKeyLines } from '@/lib/sshKeys'
import { hostToUnicode } from '@/lib/hostName'

const { t, te } = useI18n()

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

const { mutate: saveBastionDomains, isPending: saveBastionDomainsIsPending } = useMutation({
  ...updateBastionDomainsMutation(),
  onSuccess: () => {
    toast.success(t('components.bastion-info-modal.fields.http.custom-domain.success'))
    refetchBastionTargetData()
  },
  onError: (error) => {
    toast.error(describeApiError(error, { t, te }, 'bastion-domains'))
  }
})

const {
  mutateAsync: saveBastionSshAuthorizedKeysAsync,
  isPending: saveBastionSshAuthorizedKeysIsPending
} = useMutation({
  ...updateDesktopBastionAuthorizedKeysMutation(),
  onSuccess: () => {
    toast.success(t('components.bastion-info-modal.fields.ssh.authorized-keys.success'))
    refetchBastionTargetData()
  }
})

const { data: userBastionSshKey } = useQuery({
  ...getUserBastionSshKeyOptions(),
  enabled: isEditable
})
const hasOwnKey = computed(() => Boolean((userBastionSshKey.value?.ssh_key || '').trim()))

const canEditDomains = computed(
  () => isEditable.value && !!userConfig.value?.can_use_bastion_individual_domains
)
const savedDomains = computed<string[]>(() =>
  (bastionTargetData.value?.domains ?? []).map(hostToUnicode)
)
const domains = ref<string[]>([])
watch(
  savedDomains,
  (next, prev) => {
    // Any other change to the target refreshes this too; it must not discard edits.
    if (!prev || domainsChanged(next, prev)) domains.value = [...next]
  },
  { immediate: true }
)
const canSaveDomains = computed(
  () =>
    !saveBastionDomainsIsPending.value &&
    domainsChanged(domains.value, savedDomains.value) &&
    domainsOverLimit(domains.value, savedDomains.value) === 0
)
const saveDomains = () =>
  saveBastionDomains({
    path: { desktop_id: props.desktopId },
    body: { domains: cleanDomains(domains.value) }
  })

const bastionAuthorizedKeys = ref<string>('')
watch(
  () => bastionTargetData.value,
  (newVal) => {
    const keys = (newVal?.ssh.authorized_keys || []).filter(
      (k): k is string => !!k && k.trim().length > 0
    )
    bastionAuthorizedKeys.value = keys.join('\n')
  },
  { immediate: true }
)

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

const authorizedKeysSchema = z.object({
  authorizedKeys: z.string().superRefine((value, ctx) => {
    const lines = invalidAuthorizedKeyLines(value, bastionAuthorizedKeys.value)
    if (lines.length) {
      ctx.addIssue({
        code: 'custom',
        message: t('components.domain.access.bastion.ssh.authorized-keys.invalid', {
          lines: lines.join(', ')
        })
      })
    }
  })
})

const authorizedKeysForm = useForm({
  defaultValues: reactive({
    authorizedKeys: computed(() => bastionAuthorizedKeys.value)
  }),
  validators: {
    onChange: authorizedKeysSchema
  },
  onSubmit: async ({ value }) => {
    try {
      await saveBastionSshAuthorizedKeysAsync({
        body: {
          authorized_keys: value.authorizedKeys.split('\n').filter((k) => k.trim().length > 0)
        },
        path: {
          desktop_id: props.desktopId
        }
      })
    } catch (error) {
      toast.error(describeApiError(error, { t, te }, 'edit-desktop'))
    }
  }
})
const authorizedKeysIsValid = authorizedKeysForm.useStore((state) => state.isValid)
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
            <TruncatedText
              as="code"
              :title="targetId"
              class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono"
            />
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
              <TruncatedText
                as="code"
                :title="hostToUnicode(httpUrl)"
                class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono"
              />
              <a :href="httpUrl" target="_blank">
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
              <TruncatedText
                as="code"
                :title="hostToUnicode(httpsUrl)"
                class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono"
              />
              <a :href="httpsUrl" target="_blank">
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
            v-if="customDomains.length && !canEditDomains"
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
                {{ hostToUnicode(domain) }}
              </code>
            </div>
          </div>

          <div v-if="canEditDomains" class="flex flex-col gap-3 pt-4 border-t border-gray-warm-200">
            <BastionDomainsEditor
              v-model="domains"
              :saved-domains="savedDomains"
              :desktop-id="props.desktopId"
              :target-id="targetId"
              :bastion-domain="userConfig?.bastion_domain"
            />
            <Button
              type="button"
              hierarchy="primary"
              size="sm"
              icon="save-02"
              class="self-end"
              :disabled="!canSaveDomains"
              @click="saveDomains"
            >
              {{ t('components.domain.access.bastion.http-https.custom-domains.save') }}
            </Button>
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
            <TruncatedText
              as="code"
              :title="sshUrl"
              class="flex-1 bg-gray-warm-50 border border-gray-warm-200 rounded px-3 py-2 text-sm font-mono"
            />
            <CopyIcon :value="sshUrl" stroke-color="gray-warm-600" />
          </div>

          <div v-if="isEditable" class="flex flex-col gap-2 pt-2 border-t border-gray-warm-200">
            <Label class="text-sm text-gray-warm-700">
              {{ t('components.domain.access.bastion.ssh.authorized-keys.others-label') }}
            </Label>
            <Alert v-if="!hasOwnKey">
              <FeaturedIconOutline kind="outline" color="gray" />
              <AlertTitle class="font-semibold text-gray-warm-700">
                {{
                  t('components.domain.access.bastion.ssh.authorized-keys.own-key.missing.title')
                }}
              </AlertTitle>
              <AlertDescription>
                <p>
                  {{
                    t(
                      'components.domain.access.bastion.ssh.authorized-keys.own-key.missing.description'
                    )
                  }}
                </p>

                <Button
                  hierarchy="link-color"
                  class="p-0 mt-4"
                  :as="RouterLink"
                  :to="{ name: 'profile', query: { open: 'ssh' } }"
                >
                  {{
                    t('components.domain.access.bastion.ssh.authorized-keys.own-key.missing.button')
                  }}
                </Button>
              </AlertDescription>
            </Alert>
            <form
              class="flex items-start gap-2"
              @submit.prevent.stop="authorizedKeysForm.handleSubmit"
            >
              <authorizedKeysForm.Field v-slot="{ field }" name="authorizedKeys">
                <div class="flex-1 min-w-0 flex flex-col gap-1">
                  <Textarea
                    :id="field.name"
                    class="w-full bg-base-white h-32 font-mono text-sm whitespace-pre"
                    :placeholder="
                      t('components.domain.access.bastion.ssh.authorized-keys.placeholder')
                    "
                    :name="field.name"
                    :model-value="field.state.value"
                    @blur="field.handleBlur"
                    @input="field.handleChange($event.target.value)"
                  />
                  <FieldError :errors="field.state.meta.errors" />
                </div>
              </authorizedKeysForm.Field>
              <Button
                :aria-label="t('common.actions.save')"
                hierarchy="primary"
                icon="save-02"
                :disabled="saveBastionSshAuthorizedKeysIsPending || !authorizedKeysIsValid"
                type="submit"
              />
            </form>
          </div>
        </section>
      </template>
    </div>
  </Modal>
</template>
