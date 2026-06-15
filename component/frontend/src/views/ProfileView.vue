<script setup lang="ts">
import { computed, ref, shallowRef, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import {
  getUserOptions,
  getUserDetailsOptions,
  getUserConfigOptions,
  getProviderExportEnabledOptions,
  getProviderImportEnabledOptions,
  getUserVpnOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Icon } from '@/components/icon'
import { LocaleSwitch } from '@/components/locale-switch'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertModal } from '@/components/modal'
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip'
import ApiKeyModal from '@/components/profile/ApiKeyModal.vue'
import EmailVerificationModal from '@/components/profile/EmailVerificationModal.vue'
import ImportUserModal from '@/components/profile/ImportUserModal.vue'
import PasswordModal from '@/components/profile/PasswordModal.vue'
import SshPublicKeyModal from '@/components/profile/SshPublicKeyModal.vue'
import { userResetVpnMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useMutation } from '@tanstack/vue-query'
import profileImg from '@/assets/img/profile-img.svg'
import QuotaModal from '@/components/profile/QuotaModal.vue'

const { t } = useI18n()

const { data: userConfig } = useQuery({
  ...getUserConfigOptions(),
  staleTime: Infinity
})

const { isPending: isUserLoading, data: user } = useQuery({
  ...getUserOptions(),
  staleTime: Infinity
})

const { isPending: isUserDetailsLoading, data: userDetails } = useQuery({
  ...getUserDetailsOptions()
})

const { data: exportEnabled } = useQuery(
  computed(() => ({
    ...getProviderExportEnabledOptions({
      path: { provider_id: userDetails.value?.provider || 'local' }
    }),
    enabled: !!userDetails.value?.provider
  }))
)

const { data: importEnabled } = useQuery(
  computed(() => ({
    ...getProviderImportEnabledOptions({
      path: { provider_id: userDetails.value?.provider || 'local' }
    }),
    enabled: !!userDetails.value?.provider
  }))
)

const { refetch: refetchUserVpn, isFetching: userVpnIsFetching } = useQuery({
  ...getUserVpnOptions(),
  enabled: false
})

const fetchVpn = async () => {
  try {
    const { data } = await refetchUserVpn()

    if (!data) return

    const el = document.createElement('a')
    el.setAttribute('href', `data:text/plain;charset=utf-8,${encodeURIComponent(data)}`)
    el.setAttribute('download', `isard-vpn.conf`)
    el.style.display = 'none'
    document.body.appendChild(el)
    el.click()
    document.body.removeChild(el)
  } catch (e) {
    console.error(e)
  }
}

const isLoading = computed(() => isUserLoading.value || isUserDetailsLoading.value)

const userInitials = computed(() => {
  if (!user.value?.name) return '?'
  return user.value.name
    .split(' ')
    .map((n: string) => n[0])
    .join('')
    .toUpperCase()
})

const showChangePasswordButton = computed(() => {
  return userDetails.value?.provider === 'local'
})

const showChangeEmailButton = computed(() => {
  return userConfig.value?.show_change_email_button === true
})

const showApiKeyButton = computed(() => {
  return user.value?.role !== 'user'
})

const showSshKeyButton = computed(() => {
  return userConfig.value?.can_use_bastion === true
})

const showExportUserButton = computed(() => {
  return exportEnabled.value?.enabled === true
})

const showImportUserButton = computed(() => {
  return importEnabled.value?.enabled === true
})

const hasMigrations = computed(() => {
  return showExportUserButton.value || showImportUserButton.value
})

const hasUserStorage = computed(() => {
  return Boolean(userDetails.value?.user_storage?.token_web)
})

const userStorageLink = computed(() => userDetails.value?.user_storage?.token_web || '')

const showResetVpnModal = ref(false)
const resetVpnError = ref('')
const showApiKeyModal = ref(false)
const showSshKeyModal = ref(false)
const showPasswordModal = shallowRef(false)
const showEmailVerificationModal = ref(false)
const showImportUserModal = ref(false)
const showQuotaModal = shallowRef(false)
const route = useRoute()

onMounted(() => {
  if (route.query.open === 'quota') {
    showQuotaModal.value = true
  }
})
const legacyExportHref = '/export-user' // TODO: redo this page in this frontend and use router link
const { mutate: resetVpn, isPending: isResettingVpn } = useMutation(userResetVpnMutation())

const handleResetVpn = () => {
  resetVpn(
    {},
    {
      onSuccess: () => {
        resetVpnError.value = ''
        showResetVpnModal.value = false
      },
      onError: (error) => {
        const descriptionCode = error?.response?.data?.description_code
        if (descriptionCode) {
          const errorKey = `components.profile.reset-vpn-modal.errors.${descriptionCode}`
          resetVpnError.value = t(errorKey, t('components.profile.reset-vpn-modal.errors.generic'))
        } else {
          resetVpnError.value = t('components.profile.reset-vpn-modal.errors.generic')
        }
      }
    }
  )
}

watch(
  () => showResetVpnModal.value,
  (isOpen) => {
    if (isOpen) {
      resetVpnError.value = ''
    }
  }
)
</script>

<template>
  <div
    v-if="isLoading"
    class="grid grid-cols-1 md:grid-cols-[2fr_1fr] mt-6 gap-8 px-6 max-w-7xl mx-auto"
  >
    <!-- Skeleton -->
    <div class="space-y-12">
      <div>
        <div class="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-8 items-start">
          <Skeleton class="w-32 h-32 rounded-full" />
          <div class="space-y-4">
            <Skeleton class="h-5 w-24 mb-2" />
            <Skeleton class="h-11 max-w-120" />
            <Skeleton class="h-5 w-24 mb-2 mt-4" />
            <Skeleton class="h-11 max-w-120" />
            <Skeleton class="h-5 w-24 mb-2 mt-4" />
            <Skeleton class="h-11 max-w-120" />
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <div class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90">
          <Skeleton class="absolute -top-3.5 left-8 h-7 w-24 bg-base-background" />
          <div class="flex flex-col gap-3 pt-4">
            <div>
              <Skeleton class="h-4 w-48 mb-2" />
              <Skeleton class="h-9 max-w-56" />
            </div>
            <div>
              <Skeleton class="h-4 w-40 mb-2" />
              <Skeleton class="h-9 max-w-56" />
            </div>
            <div>
              <Skeleton class="h-4 w-44 mb-2" />
              <Skeleton class="h-9 max-w-56" />
            </div>
          </div>
        </div>

        <div class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90">
          <Skeleton class="absolute -top-3.5 left-8 h-7 w-28 bg-base-background" />
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4">
            <div>
              <Skeleton class="h-5 w-20 mb-1" />
              <Skeleton class="h-5 w-24" />
            </div>
            <div>
              <Skeleton class="h-5 w-24 mb-1" />
              <Skeleton class="h-5 w-20" />
            </div>
            <div>
              <Skeleton class="h-5 w-20 mb-1" />
              <Skeleton class="h-5 w-28" />
            </div>
            <div>
              <Skeleton class="h-5 w-16 mb-1" />
              <Skeleton class="h-5 w-24" />
            </div>
            <div>
              <Skeleton class="h-5 w-28 mb-1" />
              <Skeleton class="h-5 w-20" />
            </div>
            <div>
              <Skeleton class="h-5 w-12 mb-1" />
              <Skeleton class="h-5 w-16" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div
    v-else-if="user"
    class="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-8 px-6 max-w-7xl mx-auto"
  >
    <!-- Left section: Main content -->
    <div class="space-y-12">
      <!-- Section: Personal info -->
      <div>
        <h3 class="text-lg font-semibold leading-7 text-gray-warm-700 mb-6">
          {{ t('views.profile.personal-info.title') }}
        </h3>
        <div class="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-8 items-start">
          <Avatar
            size="lg"
            class="w-32 h-32 mx-auto lg:mx-0 ring-4 ring-base-white shadow-lg border border-black/10"
          >
            <AvatarImage :src="user.photo || ''" :alt="user.name" />
            <AvatarFallback class="font-bold text-9xl text-gray-warm-800 leading-none">
              {{ userInitials }}
            </AvatarFallback>
          </Avatar>

          <!-- Personal info -->
          <div class="space-y-4 mx-auto lg:mx-0">
            <label class="block text-sm font-medium text-gray-warm-700 mb-2">
              {{ t('views.profile.personal-info.fields.name') }}
            </label>
            <InputField
              v-model="user.name"
              :label="t('views.profile.personal-info.fields.name')"
              disabled
              class="max-w-120"
              icon="user-03"
            />
            <div v-if="user.email">
              <label class="block text-sm font-medium text-gray-warm-700 mb-2">
                {{ t('views.profile.personal-info.fields.email') }}
              </label>
              <div class="flex items-center gap-2">
                <InputField
                  v-model="user.email"
                  :label="t('views.profile.personal-info.fields.email')"
                  class="max-w-120"
                  disabled
                />
                <TooltipProvider v-if="showChangeEmailButton">
                  <Tooltip v-if="userDetails?.email_verified">
                    <TooltipTrigger as-child>
                      <span class="cursor-help inline-flex">
                        <Icon
                          name="check-verified-02"
                          size="md"
                          stroke-color="success-600"
                          fill-color="base-white"
                        />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent :title="t('views.profile.email-verified')" />
                  </Tooltip>
                  <Tooltip v-else-if="userDetails?.email_verified === false">
                    <TooltipTrigger as-child>
                      <span class="cursor-help inline-flex">
                        <Icon name="alert-circle" size="md" stroke-color="warning-700" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent :title="t('views.profile.email-not-verified')" />
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
            <!-- Language selector -->
            <div>
              <label class="block text-sm font-medium text-gray-warm-600 mb-2">
                {{ t('views.profile.personal-info.fields.language') }}
              </label>
              <div class="max-w-120">
                <LocaleSwitch />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Section: Security + Information -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <!-- Security  -->
        <div class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90">
          <h3
            class="absolute -top-3.5 left-8 text-lg font-semibold leading-7 text-gray-warm-700 bg-base-background px-2"
          >
            {{ t('views.profile.security.title') }}
          </h3>
          <div class="flex flex-col gap-3 pt-4">
            <div v-if="showChangePasswordButton">
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="lock-unlocked-01"
                icon-size="md"
                @click="showPasswordModal = true"
              >
                {{ t('views.profile.security.actions.change-password') }}
              </Button>
            </div>
            <div v-if="showChangeEmailButton">
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="mail-01"
                icon-size="md"
                @click="showEmailVerificationModal = true"
              >
                {{ t('views.profile.security.actions.verify-email') }}
              </Button>
            </div>
            <div v-if="showApiKeyButton">
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="key-01"
                icon-size="md"
                @click="showApiKeyModal = true"
              >
                {{ t('views.profile.security.actions.api-key') }}
              </Button>
            </div>
            <div v-if="showSshKeyButton">
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="terminal-square"
                icon-size="md"
                @click="showSshKeyModal = true"
              >
                {{ t('views.profile.security.actions.ssh-key') }}
              </Button>
            </div>
            <div>
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="shield-01"
                icon-size="md"
                @click="showResetVpnModal = true"
              >
                {{ t('views.profile.security.actions.reset-vpn') }}
              </Button>
            </div>
            <div>
              <Button
                hierarchy="secondary-gray"
                size="sm"
                class="justify-start min-w-56"
                icon="download-02"
                icon-size="md"
                :disabled="userVpnIsFetching"
                @click="fetchVpn"
              >
                {{ t('views.profile.security.actions.download-vpn') }}
              </Button>
            </div>
          </div>
        </div>

        <!-- Information -->
        <div
          class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90 bg-opacity-90"
        >
          <h3
            class="absolute -top-3.5 left-8 text-lg font-semibold leading-7 text-gray-warm-700 bg-base-background px-2"
          >
            {{ t('views.profile.information.title') }}
          </h3>
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4">
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.username') }}
              </p>
              <p class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1">
                {{ userDetails?.username || 'N/A' }}
              </p>
            </div>
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.authentication') }}
              </p>
              <p class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1">
                {{ userDetails?.provider || 'N/A' }}
              </p>
            </div>
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.category') }}
              </p>
              <p class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1">
                {{ userDetails?.category_name || 'N/A' }}
              </p>
            </div>
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.group') }}
              </p>
              <p
                class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1 max-w-40 truncate"
                :title="userDetails?.group_name"
              >
                {{ userDetails?.group_name || 'N/A' }}
              </p>
            </div>
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.secondary-groups') }}
              </p>
              <p
                class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1 max-w-40 overflow-x-hidden text-ellipsis"
                :title="userDetails?.secondary_groups_data?.map((group) => group.name).join(', ')"
              >
                {{
                  userDetails?.secondary_groups_data?.map((group) => group.name).join(', ') ||
                  (userDetails?.secondary_groups_data?.length
                    ? `${userDetails.secondary_groups_data.length} groups`
                    : '–')
                }}
              </p>
            </div>
            <div>
              <p class="text-sm leading-5 font-medium text-gray-warm-700">
                {{ t('views.profile.information.fields.role') }}
              </p>
              <p class="text-sm leading-5 font-semibold text-gray-warm-900 mt-1">
                {{ user?.role_name || 'N/A' }}
              </p>
            </div>
          </div>
          <div class="pt-6">
            <Button
              hierarchy="secondary-gray"
              size="sm"
              class="justify-start min-w-56"
              icon="bar-chart-07"
              icon-size="md"
              @click="showQuotaModal = true"
            >
              {{ t('views.profile.information.actions.view-quota') }}
            </Button>
          </div>
        </div>
      </div>

      <!-- Migrations -->
      <div v-if="hasMigrations || hasUserStorage" class="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <div
          v-if="hasMigrations"
          class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90"
        >
          <h3
            class="absolute -top-3.5 left-8 text-lg font-semibold leading-7 text-gray-warm-700 bg-base-background px-2"
          >
            {{ t('views.profile.migrations.title') }}
          </h3>
          <div class="flex flex-col gap-3 pt-4">
            <Button
              v-if="showExportUserButton"
              as="a"
              hierarchy="secondary-gray"
              size="sm"
              class="max-w-56 justify-start"
              icon="upload-01"
              icon-size="md"
              :href="legacyExportHref"
            >
              {{ t('views.profile.migrations.actions.export-user') }}
            </Button>
            <Button
              v-if="showImportUserButton"
              hierarchy="secondary-gray"
              size="sm"
              class="max-w-56 justify-start"
              icon="download-01"
              icon-size="md"
              @click="showImportUserModal = true"
            >
              {{ t('views.profile.migrations.actions.import-user') }}
            </Button>
          </div>
        </div>

        <!-- User Storage -->
        <div
          v-if="hasUserStorage"
          class="border border-gray-warm-200 rounded-lg p-8 relative bg-base-background/90"
        >
          <h3
            class="absolute -top-3.5 left-8 text-lg font-semibold leading-7 text-gray-warm-700 bg-base-background px-2"
          >
            {{ t('views.profile.storage.title') }}
          </h3>
          <div class="space-y-4 pt-4">
            <label class="block text-sm font-medium text-gray-warm-700">
              {{ t('views.profile.storage.fields.user-storage-link') }}
            </label>
            <p>
              <a
                v-if="userStorageLink"
                class="text-sm text-brand-700 hover:underline"
                :href="userStorageLink"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ userStorageLink }}
              </a>
              <span v-else class="text-sm text-gray-warm-600">–</span>
            </p>
            <Button
              as="a"
              hierarchy="secondary-gray"
              size="sm"
              class="max-w-56 justify-start"
              icon="database-01"
              icon-size="md"
              :href="userStorageLink"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ t('views.profile.storage.actions.manage-user-storage') }}
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- Decorative left image -->
    <div class="hidden xl:block">
      <div class="absolute">
        <img
          :src="profileImg"
          :alt="t('views.profile.personal-info.fields.profile-image')"
          class="object-contain h-[calc(100lvh-145px)] pb-4"
        />
      </div>
    </div>
  </div>

  <div v-else class="text-gray-500 text-center py-12">
    {{ t('views.profile.no-data') }}
  </div>

  <ApiKeyModal :open="showApiKeyModal" @update:open="(val) => (showApiKeyModal = val)" />
  <SshPublicKeyModal :open="showSshKeyModal" @update:open="(val) => (showSshKeyModal = val)" />
  <EmailVerificationModal
    :open="showEmailVerificationModal"
    :current-email="user?.email"
    @update:open="(val) => (showEmailVerificationModal = val)"
  />
  <PasswordModal v-model:open="showPasswordModal" />
  <ImportUserModal
    :open="showImportUserModal"
    @update:open="(val) => (showImportUserModal = val)"
  />
  <QuotaModal v-model:open="showQuotaModal" />

  <AlertModal
    v-model:open="showResetVpnModal"
    level="warning"
    size="md"
    :title="t('components.profile.reset-vpn-modal.title')"
    :description="t('components.profile.reset-vpn-modal.description')"
    :loading="isResettingVpn"
  >
    <template #description>
      <!-- TODO: unify how we want to display errors across the app -->
      <div v-if="resetVpnError" class="mt-3 rounded-md border border-error-200 bg-error-50 p-3">
        <p class="text-sm font-medium text-error-700">{{ resetVpnError }}</p>
      </div>
    </template>
    <template #footer>
      <Button
        hierarchy="secondary-gray"
        size="lg"
        :disabled="isResettingVpn"
        @click="showResetVpnModal = false"
      >
        {{ t('components.profile.reset-vpn-modal.cancel') }}
      </Button>
      <Button hierarchy="primary" size="lg" :disabled="isResettingVpn" @click="handleResetVpn">
        {{ t('components.profile.reset-vpn-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
