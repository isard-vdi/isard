<script setup lang="ts">
import Button from '@/components/ui/button/Button.vue'
import { AlertModal } from '@/components/modal'
import sessionRenew from '@/assets/img/modal/hourglass-renew.svg'
import sessionExpired from '@/assets/img/modal/hourglass-expired.svg'
import type { SessionModalKind } from '@/stores/session'
import { useI18n } from 'vue-i18n'

interface Props {
  open?: boolean
  loading?: boolean
  kind: SessionModalKind
}

const props = withDefaults(defineProps<Props>(), {
  level: 'warning',
  open: false
})

const emit = defineEmits(['update:open', 'renew', 'logout', 'goToLogin'])
const { t } = useI18n()
</script>

<template>
  <AlertModal
    :open="props.open"
    size="md"
    :level="props.kind === 'renew' ? 'warning' : 'danger'"
    :image="props.kind === 'renew' ? sessionRenew : sessionExpired"
    :title="t('components.session-modal.title')"
    :description="t(`components.session-modal.description.${props.kind}`)"
    :close-on-backdrop-click="false"
    :show-close-button="false"
    :class="'z-200'"
    @update:open="emit('update:open', $event)"
  >
    <template #footer>
      <div v-if="props.kind === 'renew'" class="flex w-full flex-wrap-reverse gap-2">
        <Button class="grow" size="lg" hierarchy="destructive" @click="emit('logout')">
          {{ $t('components.session-modal.options.logout') }}
        </Button>
        <Button class="grow" size="lg" hierarchy="primary" @click="emit('renew')">
          {{ $t('components.session-modal.options.renew') }}
        </Button>
      </div>
      <Button v-else size="lg" hierarchy="destructive" @click="emit('goToLogin')">
        {{ $t('components.session-modal.options.go-to-login') }}
      </Button>
    </template>
  </AlertModal>
</template>
