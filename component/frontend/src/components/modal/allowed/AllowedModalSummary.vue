<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Icon } from '@/components/icon'
import type { AllowedOption } from '.'

interface Props {
  groups: AllowedOption[]
  users: AllowedOption[]
  allGroups?: boolean
  showGroups?: boolean // When false only users can be selected, so the groups row is omitted.
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  allGroups: false,
  showGroups: true,
  disabled: false
})

const emit = defineEmits<{
  (e: 'remove-group' | 'remove-user', value: string): void
  (e: 'remove-all-groups'): void
}>()

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()

const hasGroups = computed(() => props.showGroups && (props.allGroups || props.groups.length > 0))

const groupsCountLabel = computed(() =>
  props.allGroups
    ? t('components.allowed-modal.summary.all-groups')
    : t('users.count.groups', props.groups.length)
)

const usersCountLabel = computed(() => t('users.count.users', props.users.length))

const chipClass =
  'flex h-6 max-w-[200px] shrink-0 items-center gap-1 rounded-md bg-brand-100 pl-2 pr-1 text-sm text-gray-warm-900'
const chipButtonClass =
  'flex shrink-0 items-center justify-center rounded-xs border border-transparent hover:bg-brand-200 outline-none focus-visible:border-secondary-3-600'
</script>

<template>
  <Collapsible
    v-model:open="open"
    class="mb-4 shrink-0 rounded-lg border border-gray-warm-200 bg-base-white"
    data-slot="selection-summary"
  >
    <CollapsibleTrigger
      class="flex w-full cursor-pointer flex-row items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-warm-50 focus-visible:ring-3 focus-visible:ring-gray focus-visible:outline-none"
      data-slot="selection-summary-trigger"
    >
      <Icon
        :name="open ? 'chevron-down' : 'chevron-right'"
        size="sm"
        stroke-color="gray-warm-500"
        class="shrink-0"
      />
      <span class="font-semibold text-gray-warm-700">
        {{ t('components.allowed-modal.summary.title') }}
      </span>
      <span
        v-if="props.showGroups"
        class="flex shrink-0 items-center gap-1 text-gray-warm-600"
        :title="groupsCountLabel"
        data-slot="selection-summary-groups-count"
      >
        <Icon name="users-01" size="sm" stroke-color="gray-warm-500" aria-hidden="true" />
        <span aria-hidden="true">{{
          props.allGroups ? groupsCountLabel : props.groups.length
        }}</span>
        <span class="sr-only">{{ groupsCountLabel }}</span>
      </span>
      <span
        class="flex shrink-0 items-center gap-1 text-gray-warm-600"
        :title="usersCountLabel"
        data-slot="selection-summary-users-count"
      >
        <Icon name="user-01" size="sm" stroke-color="gray-warm-500" aria-hidden="true" />
        <span aria-hidden="true">{{ props.users.length }}</span>
        <span class="sr-only">{{ usersCountLabel }}</span>
      </span>
    </CollapsibleTrigger>

    <CollapsibleContent>
      <div
        class="flex max-h-32 flex-col gap-2 overflow-y-auto border-t border-gray-warm-200 px-3 py-2"
      >
        <p v-if="!hasGroups && props.users.length === 0" class="text-sm text-gray-warm-500">
          {{ t('components.allowed-modal.summary.empty') }}
        </p>

        <div v-if="hasGroups" class="flex flex-row gap-2" data-slot="selection-summary-groups">
          <span
            class="flex h-6 w-20 shrink-0 items-center gap-1 text-xs font-semibold text-gray-warm-500"
          >
            <Icon name="users-01" size="sm" stroke-color="gray-warm-500" aria-hidden="true" />
            <span class="truncate">{{ t('components.allowed-modal.columns.groups') }}</span>
          </span>
          <div class="flex min-w-0 flex-row flex-wrap gap-1.5">
            <span v-if="props.allGroups" :class="chipClass" data-slot="summary-chip">
              <span class="truncate">{{ t('components.allowed-modal.summary.all-groups') }}</span>
              <button
                v-if="!props.disabled"
                type="button"
                :class="chipButtonClass"
                :aria-label="
                  t('components.allowed-modal.remove', {
                    name: t('components.allowed-modal.summary.all-groups')
                  })
                "
                @click="emit('remove-all-groups')"
              >
                <Icon name="x-close" size="sm" stroke-color="gray-warm-500" />
              </button>
            </span>
            <template v-else>
              <span
                v-for="group in props.groups"
                :key="group.value"
                :class="chipClass"
                :data-value="group.value"
                data-slot="summary-chip"
              >
                <span class="truncate">{{ group.label }}</span>
                <button
                  v-if="!props.disabled"
                  type="button"
                  :class="chipButtonClass"
                  :aria-label="t('components.allowed-modal.remove', { name: group.label })"
                  @click="emit('remove-group', group.value)"
                >
                  <Icon name="x-close" size="sm" stroke-color="gray-warm-500" />
                </button>
              </span>
            </template>
          </div>
        </div>

        <div
          v-if="props.users.length > 0"
          class="flex flex-row gap-2"
          data-slot="selection-summary-users"
        >
          <span
            class="flex h-6 w-20 shrink-0 items-center gap-1 text-xs font-semibold text-gray-warm-500"
          >
            <Icon name="user-01" size="sm" stroke-color="gray-warm-500" aria-hidden="true" />
            <span class="truncate">{{ t('components.allowed-modal.columns.users') }}</span>
          </span>
          <div class="flex min-w-0 flex-row flex-wrap gap-1.5">
            <span
              v-for="user in props.users"
              :key="user.value"
              :class="chipClass"
              :data-value="user.value"
              data-slot="summary-chip"
            >
              <span class="truncate">{{ user.label }}</span>
              <button
                v-if="!props.disabled"
                type="button"
                :class="chipButtonClass"
                :aria-label="t('components.allowed-modal.remove', { name: user.label })"
                @click="emit('remove-user', user.value)"
              >
                <Icon name="x-close" size="sm" stroke-color="gray-warm-500" />
              </button>
            </span>
          </div>
        </div>
      </div>
    </CollapsibleContent>
  </Collapsible>
</template>
