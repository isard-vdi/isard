<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { migrationExportUserMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { apiErrorCodes } from '@/lib/api-errors'
import { useSessionStore } from '@/stores/session'
import { useAuthStore } from '@/stores/auth'
import { TokenType } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { CopyIcon } from '@/components/icon'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Spinner } from '@/components/ui/spinner'
import { Separator } from '../ui/separator'

const props = withDefaults(
  defineProps<{
    // Reveal the logout action from the start instead of only after a token is
    // generated. Set for a voluntary export on the standalone full-page view
    // (reached from the old-frontend profile, in any mode), where logout is one
    // of the few ways out.
    showLogoutInitially?: boolean
  }>(),
  { showLogoutInitially: false }
)

const { t, te } = useI18n()
const sessionStore = useSessionStore()
const authStore = useAuthStore()

const instructions = computed(() =>
  [1, 2, 3, 4, 5].map((n) => t(`views.export-user.migration-instructions${n}`))
)

const token = ref<string>()
const errorMessage = ref('')

const { mutate: generateToken, isPending: isGenerating } = useMutation({
  ...migrationExportUserMutation(),
  onSuccess: (data) => {
    token.value = data.token
    errorMessage.value = ''
  },
  onError: (error) => {
    const [code] = apiErrorCodes(error)
    const key = `api.user_migration.errors.${code}`
    errorMessage.value = code && te(key) ? t(key) : t('views.export-user.error-generate')
  }
})

const handleGenerate = () => {
  errorMessage.value = ''
  generateToken({})
}

const handleLogout = () => {
  sessionStore.handleLogout()
}

const logoutLabel = computed(() =>
  token.value ? t('views.export-user.logout-and-continue') : t('views.export-user.logout')
)

// A forced migration (user-migration-required token) always offers logout — it
// doubles as "continue". A voluntary export from the profile (login token) only
// reveals logout once the migration token has been generated, unless the caller
// opts to show it from the start (see showLogoutInitially).
const isForced = computed(() => authStore.tokenType === TokenType.UserMigrationRequired)
const showLogout = computed(
  () => isForced.value || props.showLogoutInitially || Boolean(token.value)
)
</script>

<template>
  <div
    class="w-full max-w-3xl flex flex-col gap-8 bg-base-white px-7 py-12 border border-gray-200 shadow-md rounded-lg"
  >
    <!-- Intro + instructions -->
    <div class="space-y-6">
      <p class="text-lg text-brand-700 font-semibold">
        {{ t('views.export-user.description') }}
      </p>
      <ul class="list-disc pl-7 space-y-3 text-sm text-gray-warm-700">
        <li v-for="instruction in instructions" :key="instruction">{{ instruction }}</li>
      </ul>
    </div>

    <Separator />

    <!-- Regeneration warning -->
    <Alert class="bg-warning-50/50 border-gray-warm-300 flex items-start gap-3">
      <FeaturedIconOutline kind="outline" color="warning" size="md" class="shrink-0" />
      <div class="space-y-1 text-left">
        <AlertTitle class="text-gray-warm-900">
          {{ t('views.export-user.warning') }}
        </AlertTitle>
        <AlertDescription class="text-gray-warm-700">
          {{ t('views.export-user.migration-warning') }}
        </AlertDescription>
      </div>
    </Alert>

    <!-- Error -->
    <Alert
      v-if="errorMessage"
      variant="destructive"
      class="border-error-200 flex items-start gap-3"
    >
      <FeaturedIconOutline kind="outline" color="error" size="md" class="shrink-0" />
      <div class="space-y-1 text-left">
        <AlertTitle class="text-error-900">
          {{ t('views.export-user.error-title') }}
        </AlertTitle>
        <AlertDescription class="text-error-700">
          {{ errorMessage }}
        </AlertDescription>
      </div>
    </Alert>

    <!-- Generated token -->
    <div v-if="token" class="space-y-2">
      <p class="text-sm font-medium text-gray-warm-900">
        {{ t('views.export-user.generate-token-warning') }}
      </p>
      <div class="flex items-center gap-2">
        <InputField
          :model-value="token"
          readonly
          :aria-label="t('views.export-user.token-label')"
          class="flex-1"
        />
        <CopyIcon :value="token" size="md" />
      </div>
    </div>

    <!-- Actions -->
    <div class="flex flex-wrap items-center justify-center gap-3">
      <Button
        hierarchy="primary"
        size="md"
        icon="key-01"
        icon-size="md"
        :disabled="isGenerating || !!token"
        :aria-busy="isGenerating"
        @click="handleGenerate"
      >
        {{ t('views.export-user.generate-token') }}
      </Button>
      <Spinner v-if="isGenerating" size="sm" color="green" aria-hidden="true" />
      <span v-if="isGenerating" role="status" class="sr-only">
        {{ t('views.export-user.generating') }}
      </span>
      <Button
        v-if="showLogout"
        hierarchy="destructive"
        size="md"
        icon="log-out-01"
        icon-size="md"
        :title="t('views.export-user.logout-tooltip')"
        @click="handleLogout"
      >
        {{ logoutLabel }}
      </Button>
    </div>
  </div>
</template>
