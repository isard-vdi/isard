<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import {
  getUserConfigOptions,
  getDeploymentUserDesktopsOptions,
  getDeploymentDesktopBastionOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Icon, CopyIcon } from '@/components/icon'
import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()

interface Props {
  open?: boolean
  deploymentId: string
  userId: string
  username: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const { data: userConfig } = useQuery(getUserConfigOptions())

const {
  data: userDesktops,
  isPending: desktopsIsPending,
  isError: desktopsIsError
} = useQuery(
  getDeploymentUserDesktopsOptions({
    path: { deployment_id: props.deploymentId, user_id: props.userId }
  })
)

// Drill-down: null shows the user's desktop list, a desktop shows its
// read-only bastion access details.
const selectedDesktop = ref<{ id: string; name: string } | null>(null)

const bastionQueryOptions = computed(() => ({
  ...getDeploymentDesktopBastionOptions({
    path: {
      deployment_id: props.deploymentId,
      desktop_id: selectedDesktop.value?.id ?? ''
    }
  }),
  enabled: selectedDesktop.value !== null
}))

const {
  data: bastionData,
  isPending: bastionIsPending,
  isError: bastionIsError
} = useQuery(bastionQueryOptions)

const bastionActive = computed(
  () =>
    bastionData.value?.exists &&
    (bastionData.value?.ssh?.enabled || bastionData.value?.http?.enabled)
)

const targetIdSplit = computed(() => {
  // return the id with the last `-` replaced by `.`
  if (!bastionData.value?.id) return ''
  return (
    bastionData.value.id.split('-').slice(0, -1).join('-') +
    '.' +
    bastionData.value.id.split('-').slice(-1)[0]
  )
})

const bastionHost = computed(() => bastionData.value?.bastion_domain || window.location.hostname)

const httpUrl = computed(() => {
  const port = userConfig.value?.http_port === '80' ? '' : `:${userConfig.value?.http_port}`
  if (bastionData.value?.domain) {
    return `http://${bastionData.value.domain}${port}`
  }
  return `http://${targetIdSplit.value}.${bastionHost.value}${port}`
})
const httpsUrl = computed(() => {
  const port = userConfig.value?.https_port === '443' ? '' : `:${userConfig.value?.https_port}`
  if (bastionData.value?.domain) {
    return `https://${bastionData.value.domain}${port}`
  }
  return `https://${targetIdSplit.value}.${bastionHost.value}${port}`
})
const sshUrl = computed(() => {
  const port =
    bastionData.value?.bastion_ssh_port === '22' ? '' : ` -p ${bastionData.value?.bastion_ssh_port}`
  return `ssh ${bastionData.value?.id}@${bastionData.value?.domain || bastionHost.value}${port}`
})

const closeModal = () => {
  selectedDesktop.value = null
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    size="2xl"
    class="pt-6"
    :title="
      selectedDesktop
        ? t('components.bastion-info-modal.title', { name: selectedDesktop.name })
        : t('components.deployment-user-bastion-modal.title', { name: props.username })
    "
    :description="selectedDesktop ? '' : t('components.deployment-user-bastion-modal.description')"
    @close="closeModal"
  >
    <div class="flex flex-col gap-4 pb-4">
      <!-- Desktop list -->
      <template v-if="!selectedDesktop">
        <div
          v-if="desktopsIsPending"
          class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
        >
          <Skeleton class="h-9 w-full" />
          <Skeleton class="h-9 w-3/4" />
        </div>

        <Alert v-else-if="desktopsIsError" variant="destructive">
          <Icon name="alert-circle" stroke-color="error-700" />
          <AlertTitle>{{ t('components.deployment-user-bastion-modal.error-loading') }}</AlertTitle>
        </Alert>

        <div
          v-else-if="!userDesktops?.desktops?.length"
          class="bg-base-white p-6 rounded-lg border border-gray-warm-300 flex flex-col items-center text-center gap-2"
        >
          <Icon name="globe-04" size="lg" stroke-color="gray-warm-400" />
          <p class="font-semibold text-gray-warm-700">
            {{ t('components.deployment-user-bastion-modal.no-desktops') }}
          </p>
        </div>

        <div v-else class="flex flex-col gap-2">
          <div
            v-for="desktop in userDesktops.desktops"
            :key="desktop.id"
            class="bg-base-white p-4 rounded-lg border border-gray-warm-300 flex items-center justify-between gap-3"
          >
            <div class="flex flex-col min-w-0">
              <span class="font-semibold text-gray-warm-700 truncate">{{ desktop.name }}</span>
              <span class="text-xs text-gray-warm-500">{{ desktop.status }}</span>
            </div>
            <Button
              hierarchy="secondary-color"
              size="sm"
              icon="globe-04"
              icon-size="md"
              :title="t('components.deployment-user-bastion-modal.view-bastion')"
              @click="selectedDesktop = { id: desktop.id, name: desktop.name }"
            >
              {{ t('components.deployment-user-bastion-modal.view-bastion') }}
            </Button>
          </div>
        </div>
      </template>

      <!-- Read-only bastion details for the selected desktop -->
      <template v-else>
        <Button
          hierarchy="link-color"
          size="sm"
          icon="arrow-left"
          class="w-min -mx-1"
          @click="selectedDesktop = null"
        >
          {{ t('components.deployment-user-bastion-modal.back') }}
        </Button>

        <div
          v-if="bastionIsPending"
          class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
        >
          <Skeleton class="h-6 w-48" />
          <Skeleton class="h-9 w-full" />
          <Skeleton class="h-9 w-3/4" />
        </div>

        <Alert v-else-if="bastionIsError" variant="destructive">
          <Icon name="alert-circle" stroke-color="error-700" />
          <AlertTitle>{{ t('components.bastion-info-modal.error.title') }}</AlertTitle>
        </Alert>

        <div
          v-else-if="!bastionActive"
          class="bg-base-white p-6 rounded-lg border border-gray-warm-300 flex flex-col items-center text-center gap-2"
        >
          <Icon name="globe-04" size="lg" stroke-color="gray-warm-400" />
          <p class="font-semibold text-gray-warm-700">
            {{ t('components.bastion-info-modal.no-bastion-configured') }}
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
                {{ bastionData!.id }}
              </code>
              <CopyIcon :value="bastionData!.id ?? ''" stroke-color="gray-warm-600" />
            </div>
          </section>

          <!-- HTTP / HTTPS section -->
          <section
            v-if="bastionData!.http?.enabled"
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
          </section>

          <!-- SSH section -->
          <section
            v-if="bastionData!.ssh?.enabled"
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
          </section>
        </template>
      </template>
    </div>
  </Modal>
</template>
