<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import type { PlannedProblem, StorageRepairPlan } from '@/lib/storage-problems'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktopName: string
  plan: StorageRepairPlan | null
  errorMessage?: string | null
  describeEstimate: (estimate: PlannedProblem['problem']['estimate']) => string
  duration: (seconds: number | null | undefined) => string
  isQueued: (item: PlannedProblem) => boolean
}

const props = withDefaults(defineProps<Props>(), { open: false, errorMessage: null })

const emit = defineEmits<{ close: []; confirm: [item: PlannedProblem] }>()

const sections = computed(() => {
  const plan = props.plan
  if (!plan) return []
  return (['waits', 'quick', 'costly', 'admins'] as const)
    .map((name) => ({ name, items: plan[name] }))
    .filter((section) => section.items.length > 0)
})

const fixName = (fix?: string | null) => (fix ? t(`components.storage-problems.fix.${fix}`) : '')
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    size="lg"
    :title="t('components.storage-problems.modal.title', { name: props.desktopName })"
    :description="t('components.storage-problems.modal.description')"
    @close="emit('close')"
  >
    <template #description>
      <div class="mt-4 flex flex-col gap-4 text-left" data-testid="storage-problems">
        <section v-if="props.plan?.quickFixes.length" data-testid="quick_fixes">
          <h4 class="font-semibold">{{ t('components.storage-problems.modal.quick_fixes') }}</h4>
          <ul class="mt-1 flex flex-col gap-1">
            <li v-for="run in props.plan.quickFixes" :key="`${run.storage_id}:${run.fix}`">
              {{
                t(`components.storage-problems.quick-fix.${run.task_id ? 'queued' : 'recorded'}`, {
                  fix: fixName(run.fix)
                })
              }}
            </li>
          </ul>
        </section>
        <section v-for="section in sections" :key="section.name" :data-testid="section.name">
          <h4 class="font-semibold">
            {{ t(`components.storage-problems.modal.${section.name}`) }}
          </h4>
          <ul class="mt-1 flex flex-col gap-2">
            <li
              v-for="item in section.items"
              :key="`${item.storageId}:${item.problem.code}:${item.problem.fix}`"
              class="flex flex-col gap-1"
            >
              <span>{{ t(`components.storage-problems.code.${item.problem.code}`) }}</span>
              <template v-if="section.name === 'waits' && item.task">
                <Progress :model-value="Math.round((item.task.progress ?? 0) * 100)" />
                <span class="text-sm text-gray-warm-600">{{
                  item.task.position != null
                    ? t('components.storage-problems.queued', {
                        position: item.task.position,
                        duration: props.duration(item.task.eta_seconds)
                      })
                    : t('components.storage-problems.running')
                }}</span>
              </template>
              <span
                v-else-if="section.name === 'costly' || section.name === 'quick'"
                class="text-sm text-gray-warm-600"
                >{{ fixName(item.problem.fix) }} ·
                {{ props.describeEstimate(item.problem.estimate) }}</span
              >
              <span v-if="item.problem.estimate?.stranded" class="text-sm text-warning-600">{{
                t('components.storage-problems.stranded')
              }}</span>
              <Button
                v-if="section.name === 'costly' && item.problem.allowed"
                class="self-start"
                hierarchy="primary"
                size="sm"
                :data-testid="`run-${item.problem.fix}`"
                :disabled="props.isQueued(item)"
                @click="emit('confirm', item)"
              >
                {{
                  props.isQueued(item)
                    ? t('components.storage-problems.modal.running')
                    : t('components.storage-problems.modal.run', { fix: fixName(item.problem.fix) })
                }}
              </Button>
              <span
                v-else-if="section.name === 'costly'"
                class="text-sm text-gray-warm-600"
                data-testid="not-allowed"
                >{{ t('components.storage-problems.modal.not-allowed') }}</span
              >
            </li>
          </ul>
        </section>
        <Alert v-if="props.errorMessage" variant="destructive">
          <AlertDescription>{{ props.errorMessage }}</AlertDescription>
        </Alert>
      </div>
    </template>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.storage-problems.modal.close') }}
      </Button>
    </template>
  </AlertModal>
</template>
