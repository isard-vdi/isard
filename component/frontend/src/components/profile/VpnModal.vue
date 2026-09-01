<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { getUserVpnOptions, userResetVpnMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { CheckboxGroup } from '@/components/checkbox-group'
import { toast } from '@/components/ui/toast'
import keepVpn from '@/assets/img/modal/keep-vpn.svg'
import regenerateUrls from '@/assets/img/modal/regenerate-urls.svg'
import { describeErrorCode } from '@/lib/api-errors'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t, te } = useI18n()

const selectedOption = ref<'download' | 'reset' | undefined>(undefined)
const errorMessage = ref('')

const { refetch: refetchUserVpn, isFetching: vpnIsFetching } = useQuery({
  ...getUserVpnOptions(),
  enabled: false
})

const { mutate: resetVpn, isPending: isResettingVpn } = useMutation(userResetVpnMutation())

const isPending = computed(() => vpnIsFetching.value || isResettingVpn.value)

const confirmLabel = computed(() =>
  selectedOption.value === 'reset'
    ? t('components.profile.vpn-modal.confirm.reset')
    : t('components.profile.vpn-modal.confirm.download')
)

const confirmHierarchy = computed(() =>
  selectedOption.value === 'reset' ? 'destructive' : 'primary'
)

watch(selectedOption, () => {
  errorMessage.value = ''
})

const closeModal = () => {
  emit('update:open', false)
  selectedOption.value = undefined
  errorMessage.value = ''
}

// The modal stays open while a request is in flight, so the user always sees
// the outcome (toast on success, inline alert on error).
const handleClose = () => {
  if (isPending.value) return
  closeModal()
}

const downloadVpn = async () => {
  errorMessage.value = ''
  try {
    const { data, isError } = await refetchUserVpn()

    if (isError || typeof data !== 'string' || !data) {
      errorMessage.value = t('components.profile.vpn-modal.errors.download')
      return
    }

    const el = document.createElement('a')
    el.setAttribute('href', `data:text/plain;charset=utf-8,${encodeURIComponent(data)}`)
    el.setAttribute('download', `isard-vpn.conf`)
    el.style.display = 'none'
    document.body.appendChild(el)
    el.click()
    document.body.removeChild(el)
    toast.success(t('components.profile.vpn-modal.success.download'))
    closeModal()
  } catch (e) {
    console.error(e)
    errorMessage.value = t('components.profile.vpn-modal.errors.download')
  }
}

const handleResetVpn = () => {
  errorMessage.value = ''
  resetVpn(
    {},
    {
      onSuccess: () => {
        toast.success(t('components.profile.vpn-modal.success.reset'))
        closeModal()
      },
      onError: (error) => {
        const descriptionCode = (error as { response?: { data?: { description_code?: string } } })
          ?.response?.data?.description_code
        errorMessage.value = describeErrorCode(
          descriptionCode,
          { t, te },
          'components.profile.vpn-modal.errors'
        )
      }
    }
  )
}

const handleConfirm = () => {
  if (selectedOption.value === 'reset') {
    handleResetVpn()
  } else if (selectedOption.value === 'download') {
    downloadVpn()
  }
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.profile.vpn-modal.title')"
    :description="t('components.profile.vpn-modal.description')"
    size="3xl"
    class="pt-4"
    @close="handleClose"
  >
    <CheckboxGroup
      v-model="selectedOption"
      kind="card"
      type="single"
      direction="flex-col md:flex-row"
      :items="[
        {
          value: 'download',
          title: t('views.profile.security.actions.download-vpn'),
          description: t('components.profile.vpn-modal.options.download.description'),
          icon: 'download-02',
          image: keepVpn,
          class: 'flex-1 mb-1.5'
        },
        {
          value: 'reset',
          title: t('views.profile.security.actions.reset-vpn'),
          description: t('components.profile.vpn-modal.options.reset.description'),
          warning: t('components.profile.vpn-modal.options.reset.warning'),
          icon: 'refresh-ccw-01',
          image: regenerateUrls,
          class: 'flex-1 mb-1.5'
        }
      ]"
    />

    <!-- TODO: unify how we want to display errors across the app -->
    <div
      v-if="errorMessage"
      role="alert"
      class="mt-3 rounded-md border border-error-200 bg-error-50 p-3"
    >
      <p class="text-sm font-medium text-error-700">{{ errorMessage }}</p>
    </div>

    <template #footer>
      <Button hierarchy="link-gray" :disabled="isPending" @click="handleClose">
        {{ t('components.profile.vpn-modal.cancel') }}
      </Button>
      <div class="flex items-center gap-2">
        <Button
          :hierarchy="confirmHierarchy"
          :disabled="!selectedOption || isPending"
          @click="handleConfirm"
        >
          {{ confirmLabel }}
        </Button>
        <Spinner v-if="isPending" size="sm" color="green" />
      </div>
    </template>
  </Modal>
</template>
