<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'

import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'

import {
  getUserConfigApiV4ItemUserGetConfigGetOptions,
  getDesktopBastionApiV4ItemDesktopDesktopIdGetBastionGetOptions,
  updateDesktopBastionAuthorizedKeysApiV4ItemDesktopDesktopIdUpdateBastionAuthorizedKeysPutMutation,
  updateDesktopBastionDomainApiV4ItemDesktopDesktopIdUpdateBastionDomainPutMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Code } from '@/components/code'
import { Icon, CopyIcon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Label } from '@/components/ui/label'
import { Modal } from '@/components/modal'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopId: string
  desktopName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const {
  data: userConfig,
  isPending: userConfigIsPending,
  isError: userConfigIsError,
  error: userConfigError
} = useQuery(getUserConfigApiV4ItemUserGetConfigGetOptions())

const {
  data: bastionTargetData,
  isPending: bastionTargetDataIsPending,
  isError: bastionTargetDataIsError,
  error: bastionTargetDataError,
  refetch: refetchBastionTargetData
} = useQuery(
  getDesktopBastionApiV4ItemDesktopDesktopIdGetBastionGetOptions({
    path: {
      desktop_id: props.desktopId
    }
  })
)

const {
  mutate: saveBastionHttpDomain,
  mutateAsync: saveBastionHttpDomainAsync,
  isPending: saveBastionHttpDomainIsPending,
  isError: saveBastionHttpDomainIsError,
  error: saveBastionHttpDomainError
} = useMutation({
  ...updateDesktopBastionDomainApiV4ItemDesktopDesktopIdUpdateBastionDomainPutMutation(),
  onSuccess: () => {
    refetchBastionTargetData()
  }
})

const {
  mutate: saveBastionSshAuthorizedKeys,
  mutateAsync: saveBastionSshAuthorizedKeysAsync,
  isPending: saveBastionSshAuthorizedKeysIsPending,
  isError: saveBastionSshAuthorizedKeysIsError,
  error: saveBastionSshAuthorizedKeysError
} = useMutation({
  ...updateDesktopBastionAuthorizedKeysApiV4ItemDesktopDesktopIdUpdateBastionAuthorizedKeysPutMutation(),
  onSuccess: () => {
    refetchBastionTargetData()
  }
})

const bastionDomain = ref<string>('')
const bastionAuthorizedKeys = ref<string>('')
watch(
  () => bastionTargetData.value,
  (newVal) => {
    bastionDomain.value = newVal?.domain || ''
    bastionAuthorizedKeys.value = newVal?.ssh.authorized_keys?.join('\n') || ''
  },
  { immediate: true }
)

const bastionModalDnsAlertOpen = ref(false)

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
  const port = userConfig.value?.http_port === '80' ? '' : `:${userConfig.value?.http_port}`
  if (bastionTargetData.value?.domain) {
    return `http://${bastionTargetData.value?.domain}${port}`
  }
  return `http://${targetIdSplit.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})
const httpsUrl = computed(() => {
  const port = userConfig.value?.https_port === '443' ? '' : `:${userConfig.value?.https_port}`
  if (bastionTargetData.value?.domain) {
    return `https://${bastionTargetData.value.domain}${port}`
  }
  return `https://${targetIdSplit.value}.${userConfig.value?.bastion_domain || window.location.hostname}${port}`
})
const sshUrl = computed(() => {
  const port =
    userConfig.value?.bastion_ssh_port === '22' ? '' : ` -p ${userConfig.value?.bastion_ssh_port}`
  return `ssh ${bastionTargetData.value?.id}@${bastionTargetData.value?.domain || userConfig.value?.bastion_domain || window.location.hostname}${port}`
})

const closeModal = () => {
  bastionModalDnsAlertOpen.value = false
  bastionDomain.value = ''
  bastionAuthorizedKeys.value = ''
  emit('close')
}

const isPending = userConfigIsPending || bastionTargetDataIsPending
const isError = userConfigIsError || bastionTargetDataIsError

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
    console.log('Submitting authorized keys form with value:', value)
    await saveBastionSshAuthorizedKeysAsync({
      body: {
        authorized_keys: value.authorizedKeys.split('\n')
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
    class="w-160 max-w-160 overflow-y-show pt-4 pb-1"
    :title="t('components.bastion-info-modal.title', { name: props.desktopName })"
    @close="closeModal"
  >
    <Skeleton v-if="isPending" class="h-6 w-60" />
    <div v-else-if="isError" class="flex flex-col gap-4 w-full bg-error-300 p-4 rounded">
      <p v-if="userConfigIsError" class="text-error-700">
        {{ t('components.bastion-info-modal.error-loading-user-config') }}:
        {{ userConfigError?.message || 'Unknown error' }}
      </p>

      <p v-if="bastionTargetDataIsError" class="text-error-700">
        {{ t('components.bastion-info-modal.error-loading-bastion-data') }}:
        {{ bastionTargetDataError?.message || 'Unknown error' }}
      </p>
    </div>
    <p v-else-if="!bastionTargetData" class="text-warning-500">
      {{ t('components.bastion-info-modal.no-bastion-configured') }}
    </p>
    <div v-else class="flex flex-col gap-4 w-full">
      <div class="flex flex-col gap-2">
        <div class="flex flex-row items-center gap-2 w-full">
          <Label class="text-nowrap font-bold text-muted-foreground">{{
            t('components.bastion-info-modal.fields.target-id.title')
          }}</Label>
          <Separator />
        </div>
        <div class="flex flex-row items-center gap-4 w-full">
          <p class="text-nowrap">{{ bastionTargetData.id }}</p>
          <CopyIcon :value="bastionTargetData.id" stroke-color="gray-warm-600" />
        </div>
      </div>

      <div v-if="bastionTargetData.http.enabled" class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <div class="flex flex-row items-center gap-2 w-full">
            <Label class="text-nowrap font-bold text-muted-foreground">{{
              t('components.domain.access.bastion.http-https.label')
            }}</Label>
            <Separator />
          </div>
          <div class="flex flex-row items-center gap-4 w-full">
            <p class="text-nowrap truncate">{{ httpUrl }}</p>
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
          <div class="flex flex-row items-center gap-4 w-full">
            <p class="text-nowrap truncate">{{ httpsUrl }}</p>
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

        <div v-if="true" class="flex flex-col w-full">
          <div class="flex flex-row items-center gap-2 w-full mb-2">
            <Label class="text-nowrap font-bold text-muted-foreground">{{
              t('components.domain.access.bastion.http-https.custom-domains.label')
            }}</Label>
            <Separator />
          </div>
          <!-- TODO: Allow multiple domains. Can use as reference bastion config form -->
          <form
            class="flex flex-row items-center gap-2 w-full"
            @submit.prevent.stop="domainNameForm.handleSubmit"
          >
            <domainNameForm.Field v-slot="{ field }" name="domainName">
              <InputField
                :id="field.name"
                class="w-full"
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
          <div class="flex flex-col items-start gap-2">
            <Label
              class="cursor-pointer gap-1 ml-2 text-gray-warm-600"
              @click="bastionModalDnsAlertOpen = !bastionModalDnsAlertOpen"
              >{{
                bastionModalDnsAlertOpen
                  ? t('components.domain.access.bastion.http-https.custom-domains.less-details')
                  : t('components.domain.access.bastion.http-https.custom-domains.more-details')
              }}
              <Icon
                :name="bastionModalDnsAlertOpen ? 'chevron-up' : 'chevron-down'"
                stroke-color="gray-warm-600"
              />
            </Label>

            <Alert v-if="bastionModalDnsAlertOpen" class="bg-white border-gray-warm-300">
              <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
                t('components.domain.access.bastion.http-https.custom-domains.alert.title')
              }}</AlertTitle>

              <i18n-t
                keypath="components.domain.access.bastion.http-https.custom-domains.alert.description"
                tag="AlertDescription"
                class="text-gray-warm-700"
              >
                <template #cname-url>
                  <Code>{{
                    `${bastionTargetData!.desktop_id}.${userConfig?.bastion_domain}`
                  }}</Code>
                  <div class="inline-block mx-1">
                    <CopyIcon
                      class="inline-block"
                      :value="`${bastionTargetData!.desktop_id}.${userConfig?.bastion_domain}`"
                      size="sm"
                      stroke-color="gray-warm-600"
                    />
                  </div>
                </template>
              </i18n-t>
            </Alert>
          </div>
        </div>
      </div>

      <div v-if="bastionTargetData?.ssh.enabled" class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <div class="flex flex-row items-center gap-2 w-full">
            <Label class="text-nowrap font-bold text-muted-foreground">{{
              t('components.domain.access.bastion.ssh.label')
            }}</Label>
            <Separator />
          </div>
          <div class="flex flex-row items-center gap-4 w-full">
            <p class="text-nowrap">{{ sshUrl }}</p>
            <CopyIcon :value="sshUrl" stroke-color="gray-warm-600" />
          </div>
        </div>

        <div v-if="true" class="flex flex-col gap-2">
          <div class="flex flex-row items-center gap-2 w-full">
            <Label class="text-nowrap font-bold text-muted-foreground">{{
              t('components.domain.access.bastion.ssh.authorized-keys.label')
            }}</Label>
            <Separator />
          </div>
          <form
            class="flex flex-row items-start gap-2 w-full"
            @submit.prevent.stop="authorizedKeysForm.handleSubmit"
          >
            <authorizedKeysForm.Field v-slot="{ field }" name="authorizedKeys">
              <Textarea
                :id="field.name"
                class="w-full bg-base-white h-32 text-nowrap mb-1"
                :placeholder="t('components.domain.access.bastion.ssh.authorized-keys.placeholder')"
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
      </div>
    </div>
  </Modal>
</template>
