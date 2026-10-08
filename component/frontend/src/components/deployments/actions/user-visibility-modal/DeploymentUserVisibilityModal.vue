<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { getDeploymentOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { DataTable } from '@/components/data-table'
import { Modal } from '@/components/modal'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toast'
import { TruncatedText } from '@/components/truncated-text'
import { useDeploymentVisibility } from '@/composables/useDeploymentVisibility'
import { runningCount, userDesktops, type MatrixDesktop } from '@/lib/deployment-visibility'
import { desktopActionsData, desktopStatusLabel } from '@/lib/desktops'

interface Props {
  open?: boolean
  deploymentId: string
  userId: string
  username: string
}

const props = withDefaults(defineProps<Props>(), { open: false })

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
}>()

const i18n = useI18n()
const { t } = i18n

const statusLabel = (status?: string) => desktopStatusLabel(status, i18n)
const statusIcon = (status?: string) => desktopActionsData(status ?? '').text

// Same query as the deployment page, so the rows follow its websocket patches.
const { data: deployment, isPending } = useQuery(
  getDeploymentOptions({ path: { deployment_id: props.deploymentId } })
)

const desktops = computed<MatrixDesktop[]>(() => {
  const user = deployment.value?.users.find((entry) => entry.id === props.userId)
  return user ? userDesktops(user) : []
})

/** Only the desktops the user has changed; the rest read the live value. */
const draft = ref<Record<string, boolean>>({})

const isVisible = (desktop: MatrixDesktop) => draft.value[desktop.desktop_id] ?? desktop.visible

const rows = computed(() =>
  desktops.value.map((desktop) => ({
    id: desktop.desktop_id,
    name: desktop.name ?? '',
    status: desktop.status ?? undefined,
    visible: isVisible(desktop)
  }))
)

const toShow = computed(() => desktops.value.filter((d) => !d.visible && isVisible(d)))
const toHide = computed(() => desktops.value.filter((d) => d.visible && !isVisible(d)))
const hasChanges = computed(() => toShow.value.length + toHide.value.length > 0)
const runningToHide = computed(() => runningCount(toHide.value))

const visibleInDraft = computed(() => rows.value.filter((row) => row.visible).length)
const masterState = computed<boolean | 'indeterminate'>(() => {
  if (!rows.value.length || visibleInDraft.value === 0) return false
  return visibleInDraft.value === rows.value.length ? true : 'indeterminate'
})

const saving = ref(false)
const errorMessage = ref<string | null>(null)

const toggle = (desktopId: string) => {
  if (saving.value) return
  const desktop = desktops.value.find((d) => d.desktop_id === desktopId)
  if (desktop) draft.value = { ...draft.value, [desktopId]: !isVisible(desktop) }
}

// A mixed set turns fully visible, like the aggregate toggles elsewhere.
const toggleAll = () => {
  if (saving.value) return
  const visible = masterState.value !== true
  draft.value = Object.fromEntries(desktops.value.map((d) => [d.desktop_id, visible]))
}

const { mutateAsync: setVisibility } = useDeploymentVisibility(() => props.deploymentId)

const save = async (stopStartedDomains: boolean) => {
  saving.value = true
  errorMessage.value = null
  const path = { deployment_id: props.deploymentId }
  try {
    if (toShow.value.length) {
      await setVisibility({
        path,
        body: { visible: true, desktop_ids: toShow.value.map((d) => d.desktop_id) }
      })
    }
    if (toHide.value.length) {
      await setVisibility({
        path,
        body: {
          visible: false,
          desktop_ids: toHide.value.map((d) => d.desktop_id),
          stop_started_domains: stopStartedDomains
        }
      })
    }
    toast.success(t('components.deployments.user-visibility-modal.success'))
    handleClose()
  } catch {
    errorMessage.value = t('views.deployment.visibility.toast.error')
  } finally {
    saving.value = false
  }
}

const headers = computed(() => [
  { name: '', key: 'visible', width: 'max-content' },
  {
    name: t('components.deployments.user-visibility-modal.headers.desktop'),
    key: 'name',
    headerClass: 'w-full',
    sortable: true
  },
  {
    name: t('components.deployments.user-visibility-modal.headers.status'),
    key: 'status',
    width: 'minmax(var(--spacing-32), var(--spacing-48))',
    sortable: true
  }
])

const handleClose = () => {
  draft.value = {}
  errorMessage.value = null
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    size="3xl"
    :close-on-backdrop-click="!saving"
    :title="t('components.deployments.user-visibility-modal.title', { name: props.username })"
    :description="t('components.deployments.user-visibility-modal.description')"
    @close="handleClose"
  >
    <div class="flex flex-col gap-4 pb-2">
      <Alert v-if="errorMessage" variant="destructive">
        <AlertDescription>{{ errorMessage }}</AlertDescription>
      </Alert>

      <Alert v-if="runningToHide > 0" variant="warning">
        <AlertDescription>
          {{ t('views.deployment.visibility.confirm.running', runningToHide) }}
        </AlertDescription>
      </Alert>

      <div v-if="isPending" class="flex flex-col gap-2">
        <Skeleton v-for="index in 2" :key="index" class="h-12 w-full" />
      </div>

      <DataTable
        v-else
        :headers="headers"
        :rows="rows"
        :page-size="rows.length || 1"
        :is-clickable="true"
        cell-class="h-14"
        @row-click="(row) => toggle(row.id as string)"
      >
        <template #head-visible>
          <Checkbox
            :model-value="masterState"
            :indeterminate="masterState === 'indeterminate'"
            :disabled="saving || rows.length === 0"
            :aria-label="t('components.deployments.user-visibility-modal.select-all')"
            size="md"
            class="bg-base-white"
            @update:model-value="toggleAll"
          />
        </template>

        <template #cell-visible="{ row }">
          <span class="flex items-center" @click.stop>
            <Checkbox
              :model-value="row.visible as boolean"
              :disabled="saving"
              :aria-label="row.name as string"
              size="md"
              class="bg-base-white"
              @update:model-value="toggle(row.id as string)"
            />
          </span>
        </template>

        <template #cell-name="{ row }">
          <div class="flex min-w-0 items-center gap-2">
            <Icon
              :name="row.visible ? 'eye' : 'eye-off'"
              size="md"
              class="shrink-0"
              :stroke-color="row.visible ? 'gray-warm-700' : 'gray-warm-400'"
              aria-hidden="true"
            />
            <TruncatedText
              :title="row.name as string"
              class="text-sm font-semibold text-gray-warm-900"
            />
          </div>
        </template>

        <template #cell-status="{ row }">
          <div class="flex items-center gap-2 text-sm font-medium text-gray-warm-700">
            <Icon
              v-if="statusIcon(row.status as string)"
              :name="statusIcon(row.status as string)!.icon"
              size="md"
              class="shrink-0"
              :class="statusIcon(row.status as string)!.iconClass"
              :stroke-color="statusIcon(row.status as string)!.iconColor"
            />
            {{ statusLabel(row.status as string) }}
          </div>
        </template>

        <template #empty>
          {{ t('components.deployments.user-visibility-modal.empty') }}
        </template>
      </DataTable>
    </div>

    <template #footer>
      <Button hierarchy="link-gray" :disabled="saving" @click="handleClose">
        {{ t('views.deployment.visibility.confirm.cancel') }}
      </Button>
      <template v-if="runningToHide > 0">
        <Button hierarchy="secondary-gray" :disabled="saving" @click="save(false)">
          {{ t('views.deployment.visibility.confirm.only-hide') }}
        </Button>
        <Button hierarchy="destructive" :disabled="saving" @click="save(true)">
          {{ t('views.deployment.visibility.confirm.hide-and-stop') }}
        </Button>
      </template>
      <Button v-else hierarchy="primary" :disabled="saving || !hasChanges" @click="save(false)">
        <Icon
          v-if="saving"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.deployments.user-visibility-modal.save') }}
      </Button>
    </template>
  </Modal>
</template>
