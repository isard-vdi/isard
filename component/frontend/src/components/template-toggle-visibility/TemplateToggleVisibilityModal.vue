<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'

import { toggleTemplateEnabledMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()

interface Props {
  open?: boolean
  action?: 'show' | 'hide'
  data?: {
    id: string
    name: string
  }
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  action: 'show',
  data: undefined
})

const emit = defineEmits<{
  close: []
}>()

const {
  mutate: toggleTemplate,
  mutateAsync: toggleTemplateAsync,
  isPending: toggleTemplateIsPending,
  isError: toggleTemplateIsError,
  error: toggleTemplateError
} = useMutation({
  ...toggleTemplateEnabledMutation(),
  onSuccess: () => {
    emit('close')
  }
})
</script>

<template>
  <AlertModal
    :open="props.open"
    :level="props.action === 'show' ? 'info' : 'warning'"
    size="lg"
    :title="
      t(`components.templates.change-visibility-confirmation-modal.${props.action}.title`, {
        kind: t('domains.templates', 1),
        name: props.data?.name
      })
    "
    :description="
      t(`components.templates.change-visibility-confirmation-modal.${props.action}.description`)
    "
    @close="emit('close')"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t(`components.templates.change-visibility-confirmation-modal.cancel`)
      }}</Button>

      <Button
        v-if="props.data"
        hierarchy="destructive"
        :disabled="toggleTemplateIsPending"
        @click="
          toggleTemplate({
            path: { template_id: props.data.id }
          })
        "
      >
        <Icon
          v-if="toggleTemplateIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t(`components.templates.change-visibility-confirmation-modal.${props.action}.confirm`) }}
      </Button>
      <Skeleton v-else class="h-full w-32" />
    </template>
  </AlertModal>
</template>
