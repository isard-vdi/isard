<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery, useMutation } from '@tanstack/vue-query'
import Modal from '@/components/modal/Modal.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { InputField } from '@/components/input-field'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Icon, CopyIcon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import DatePicker from '@/components/date-picker/DatePicker.vue'
import { getLocalTimeZone, today, type DateValue } from '@internationalized/date'
import { useI18n } from 'vue-i18n'
import {
  getUserApiKeyOptions,
  expireUserApiKeyMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { generateApiKeyMutation } from '@/gen/oas/authentication/@tanstack/vue-query.gen'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const showApiKey = ref(false)
const selectedDate = ref<DateValue | null>(null)
const generatedApiKey = ref<string | undefined>(undefined)
const errorMessage = ref<string>('')

const initializeDefaultDate = () => {
  const tz = getLocalTimeZone()
  selectedDate.value = today(tz).add({ months: 1 })
}

initializeDefaultDate()

watch(
  () => props.open,
  (newVal) => {
    if (!newVal) {
      showApiKey.value = false
      initializeDefaultDate()
      generatedApiKey.value = undefined
    }
  }
)

const handleClose = () => {
  emit('update:open', false)
}

const {
  data: userApiKey,
  refetch: refetchUserApiKey,
  error: userApiKeyError
} = useQuery({
  ...getUserApiKeyOptions(),
  enabled: computed(() => props.open)
})

watch(
  () => userApiKeyError.value,
  (error: unknown) => {
    if (error) {
      const descriptionCode =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { description_code?: string } } }).response?.data
              ?.description_code
          : undefined

      if (descriptionCode) {
        const errorKey = `components.profile.api-key-modal.errors.${descriptionCode}`
        errorMessage.value = t(errorKey, t('components.profile.api-key-modal.alert.error-fetch'))
      } else {
        errorMessage.value = t('components.profile.api-key-modal.alert.error-fetch')
      }
    }
  }
)

const { mutateAsync: generateApiKey, isPending: isGeneratingApiKey } =
  useMutation(generateApiKeyMutation())

const { mutateAsync: expireApiKey, isPending: isExpiringApiKey } = useMutation(
  expireUserApiKeyMutation()
)

const handleGenerateKey = async () => {
  if (!selectedDate.value) return
  const tz = getLocalTimeZone()
  const expirationDate = selectedDate.value.toDate(tz)
  const minutes = Math.max(1, Math.floor((expirationDate.getTime() - Date.now()) / 1000 / 60))

  errorMessage.value = ''

  try {
    const data = await generateApiKey({ body: { expiration_minutes: minutes } })
    generatedApiKey.value = data.api_key
    await refetchUserApiKey()
  } catch (error: unknown) {
    // Authentication service - show only generic error
    errorMessage.value = t('components.profile.api-key-modal.alert.error-generate')
  }
}

const handleExpireKey = async () => {
  errorMessage.value = ''

  try {
    await expireApiKey({})
    generatedApiKey.value = undefined
    await refetchUserApiKey()
  } catch (error: unknown) {
    const descriptionCode =
      error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { description_code?: string } } }).response?.data
            ?.description_code
        : undefined

    if (descriptionCode) {
      const errorKey = `components.profile.api-key-modal.errors.${descriptionCode}`
      errorMessage.value = t(errorKey, t('components.profile.api-key-modal.alert.error-expire'))
    } else {
      errorMessage.value = t('components.profile.api-key-modal.alert.error-expire')
    }
  }
}

const toggleShowApiKey = () => {
  showApiKey.value = !showApiKey.value
}

const tz = getLocalTimeZone()
const minValue = computed(() => today(tz).add({ days: 1 }))
const maxValue = computed(() => today(tz).add({ years: 1 }))
const defaultPlaceholder = computed(() => today(tz).add({ months: 1 }))

const { locale, t } = useI18n()

const formattedExpireDate = computed(() => {
  const expireDate = apiKeyExpireDate.value
  if (!expireDate) return ''

  const date = new Date(expireDate)
  return date.toLocaleDateString(locale.value || undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
})

const hasKey = computed(() => {
  if (generatedApiKey.value && generatedApiKey.value.length > 0) return true
  return userApiKey.value?.exists === true
})

const apiKeyExpireDate = computed(() => {
  if (userApiKey.value?.expires) {
    return new Date(userApiKey.value.expires * 1000).toISOString()
  }
  return undefined
})

const isKeyExpired = computed(() => {
  const expireDate = apiKeyExpireDate.value
  if (!expireDate) return false
  const expire = new Date(expireDate)
  const now = new Date()
  return expire.getTime() < now.getTime()
})

const isActionDisabled = computed(() => isGeneratingApiKey.value || isExpiringApiKey.value)

const existingDescription = computed(() =>
  isKeyExpired.value
    ? t('components.profile.api-key-modal.existing-key.description-expired')
    : t('components.profile.api-key-modal.existing-key.description-2')
)

const expireButtonLabel = computed(() =>
  isKeyExpired.value
    ? t('components.profile.api-key-modal.existing-key.buttons.delete')
    : t('components.profile.api-key-modal.existing-key.buttons.expire')
)
</script>

<template>
  <Modal
    :open="props.open"
    :title="$t('components.profile.api-key-modal.title')"
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
            {{ $t('components.profile.api-key-modal.alert.error-title') }}
          </AlertTitle>
          <AlertDescription class="text-error-700">
            {{ errorMessage }}
          </AlertDescription>
        </div>
      </Alert>

      <Alert
        v-if="hasKey && isKeyExpired"
        class="bg-base-white border-gray-warm-300 flex items-start gap-3"
      >
        <FeaturedIconOutline kind="outline" color="error" size="md" class="shrink-0" />
        <div class="space-y-1 text-left">
          <AlertTitle class="text-gray-warm-900">
            {{ $t('components.profile.api-key-modal.alert.expired-title') }}
          </AlertTitle>
          <AlertDescription class="text-gray-warm-900">
            {{ $t('components.profile.api-key-modal.alert.expired') }}
          </AlertDescription>
        </div>
      </Alert>

      <!-- No key, show generator -->
      <div v-if="!hasKey" class="space-y-4">
        <h5 class="text-lg font-semibold text-gray-warm-900">
          {{ $t('components.profile.api-key-modal.new-key.title') }}
        </h5>

        <p class="text-sm text-gray-warm-700">
          {{ $t('components.profile.api-key-modal.new-key.description') }}
        </p>

        <div class="mt-2 flex flex-wrap md:flex-nowrap items-end gap-3 md:gap-4 pb-2">
          <div class="w-full md:w-2/3 flex-shrink-0">
            <DatePicker
              v-model="selectedDate"
              :min-value="minValue"
              :max-value="maxValue"
              :default-placeholder="defaultPlaceholder"
              :placeholder="$t('components.profile.api-key-modal.new-key.buttons.expiration-label')"
              :locale="locale"
            />
          </div>

          <div class="flex items-center gap-2">
            <Button
              hierarchy="primary"
              size="md"
              class="flex-shrink-0"
              :disabled="isActionDisabled"
              @click="handleGenerateKey"
            >
              {{ $t('components.profile.api-key-modal.new-key.buttons.generate') }}
            </Button>
            <Spinner v-if="isGeneratingApiKey" size="sm" color="green" />
          </div>
        </div>
      </div>

      <!-- Has key,show key info -->
      <div v-else class="space-y-4">
        <Alert
          v-if="!isKeyExpired"
          class="bg-base-white border-gray-warm-300 flex items-start gap-3"
        >
          <FeaturedIconOutline kind="outline" color="warning" size="md" class="shrink-0" />
          <div class="space-y-1 text-left">
            <AlertTitle class="text-gray-warm-900">
              {{ $t('components.profile.api-key-modal.alert.valid-title') }}
            </AlertTitle>
            <AlertDescription class="text-gray-warm-900">
              {{
                $t('components.profile.api-key-modal.alert.valid-description', {
                  date: formattedExpireDate
                })
              }}
            </AlertDescription>
          </div>
        </Alert>

        <p class="text-sm text-gray-warm-700">
          {{ existingDescription }}
        </p>

        <div v-if="generatedApiKey" class="space-y-2">
          <p class="text-sm font-medium text-gray-warm-900">
            {{ $t('components.profile.api-key-modal.new-key.warning') }}
          </p>

          <div class="flex items-center gap-2">
            <InputField
              :model-value="generatedApiKey"
              :type="showApiKey ? 'text' : 'password'"
              readonly
              class="flex-1"
            />

            <Icon
              :name="showApiKey ? 'eye-off' : 'eye'"
              size="md"
              class="cursor-pointer text-gray-warm-700 hover:text-gray-warm-900"
              :title="$t('components.profile.api-key-modal.new-key.buttons.show')"
              @click="toggleShowApiKey"
            />

            <CopyIcon :value="generatedApiKey ?? ''" size="md" />
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div v-if="hasKey" class="w-full flex justify-center px-6">
        <div class="flex items-center gap-2">
          <Button
            hierarchy="destructive"
            size="md"
            class="min-w-[140px]"
            :title="$t('components.profile.api-key-modal.existing-key.buttons.expire-tooltip')"
            :disabled="isActionDisabled"
            @click="handleExpireKey"
          >
            {{ expireButtonLabel }}
          </Button>
          <Spinner v-if="isExpiringApiKey" size="sm" color="red" />
        </div>
      </div>
    </template>
  </Modal>
</template>
