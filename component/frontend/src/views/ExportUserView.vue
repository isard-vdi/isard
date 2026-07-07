<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import {
  getProviderExportEnabledOptions,
  getUserConfigOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useAuthStore } from '@/stores/auth'
import { TokenType } from '@/lib/auth'
import { SinglePageLayout } from '@/layouts/single-page'
import { ExportUserContent } from '@/components/export-user'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isStandalone = computed(() => route.name === 'export-user-standalone')

const isVoluntary = computed(() => authStore.tokenType === TokenType.Login)
const provider = computed(() => authStore.user?.provider ?? '')

const { data: exportConfig, isPending } = useQuery({
  ...getProviderExportEnabledOptions({ path: { provider_id: provider.value } }),
  enabled: computed(() => isVoluntary.value && !!provider.value)
})

// Needed to decide how to reject a denied export: in deprecated mode the user
// belongs to the Vue 2 app, so we bounce them there instead of the Vue 3 403.
const { data: userConfig, isPending: isConfigPending } = useQuery({
  ...getUserConfigOptions(),
  enabled: computed(() => isVoluntary.value)
})

const isChecking = computed(
  () => isVoluntary.value && !!provider.value && (isPending.value || isConfigPending.value)
)
const canExport = computed(() => !isVoluntary.value || exportConfig.value?.enabled === true)

// The standalone page is a full-page dead end (no app chrome), reached by a
// voluntary export from the old-frontend profile in any mode. Give it a "go
// back" button and show logout from the start so the user isn't trapped.
const isVoluntaryStandalone = computed(() => isVoluntary.value && isStandalone.value)

watch(
  [isChecking, canExport],
  () => {
    // Fail closed: once the check resolves, a disabled/missing/failed gate
    // rejects the user.
    if (isChecking.value || canExport.value) return

    if (userConfig.value?.frontend_mode === 'deprecated') {
      window.location.assign('/')
      return
    }
    router.replace({ name: 'error', params: { code: '403' } })
  },
  { immediate: true }
)
</script>

<template>
  <div v-if="isChecking" class="flex min-h-screen items-center justify-center">
    <Spinner size="md" color="green" />
  </div>

  <template v-else-if="canExport">
    <SinglePageLayout v-if="isStandalone" :go-back="isVoluntaryStandalone">
      <template #title>
        <h1
          class="mt-[46px] mb-[32px] text-center text-display-md font-bold text-brand-700 bg-base-background p-2 w-fit mx-auto rounded-lg"
        >
          {{ t('views.export-user.title') }}
        </h1>
      </template>
      <template #main>
        <img
          src="@/assets/img/export.svg"
          alt=""
          aria-hidden="true"
          class="fixed bottom-0 left-0 -z-10 h-1/2 invisible md:visible"
        />
        <div class="flex justify-center">
          <ExportUserContent :show-logout-initially="isVoluntaryStandalone" />
        </div>
      </template>
    </SinglePageLayout>

    <div v-else class="w-fit flex justify-center mx-auto mt-25">
      <img
        src="@/assets/img/export.svg"
        alt=""
        aria-hidden="true"
        class="fixed bottom-0 right-0 -z-10 h-1/2 invisible md:visible"
      />
      <div class="flex justify-center">
        <!-- Embedded view: isStandalone is false here, so logout stays hidden
             until a token is generated (prop defaults to false). -->
        <ExportUserContent />
      </div>
    </div>
  </template>
</template>
