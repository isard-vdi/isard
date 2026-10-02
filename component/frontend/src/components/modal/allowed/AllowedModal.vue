<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { refDebounced } from '@vueuse/core'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import AllowedModalColumn from './AllowedModalColumn.vue'
import AllowedModalGroupFilter from './AllowedModalGroupFilter.vue'
import AllowedModalSummary from './AllowedModalSummary.vue'
import type { AllowedOption, AllowedSelection } from '.'
import type { AvailableUser } from '@/gen/oas/apiv4'
import {
  getAvailableGroupsForCategoryOptions,
  searchUsersInCategoryOptions,
  searchUsersInCategoryQueryKey,
  getDeploymentAllowedOptions,
  getDeploymentAllowedQueryKey,
  getMediaAllowedTableOptions,
  getMediaAllowedTableQueryKey,
  getTemplateAllowedOptions,
  getTemplateAllowedQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Field, FieldContent, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FeaturedIconOutline } from '@/components/icon/featured-outline/index.js'

interface Props {
  open: boolean
  loading?: boolean
  title?: string // Overrides the default title.
  description?: string // Overrides the description derived from itemType.
  warning?: string // Shown as an alert above the columns.
  itemId?: string // ID of the item being edited. Used to fetch current allowed settings.
  itemType?: 'template' | 'deployment' | 'media' // Type of the item being edited. Used to determine API endpoint and description.
  selection?: AllowedSelection // Selection to open with when the item does not exist yet
  requireSelection?: boolean // Block saving if the selection is empty
  supportsEveryone?: boolean // Whether an empty array means "everyone"
  usersOnly?: boolean // Only users can be picked; groups become browse-only navigation
  roles?: string[] // Restrict the pickable users to these role ids
  preselectedUsers?: AllowedOption[] // Users shown in the users column when nothing is being browsed or searched
  error?: string // Error message to show in the footer.
  readonly?: boolean // Show the current selection without allowing changes.
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  loading: false,
  title: '',
  description: '',
  warning: '',
  itemId: undefined,
  itemType: undefined,
  selection: undefined,
  requireSelection: false,
  supportsEveryone: true,
  usersOnly: false,
  roles: undefined,
  preselectedUsers: undefined,
  error: '',
  readonly: false
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', selection: AllowedSelection): void
}>()

const { t } = useI18n()

const everyoneEnabled = computed(() => props.supportsEveryone && !props.usersOnly)

const roleQuery = computed(() => (props.roles?.length ? { roles: [...props.roles] } : undefined))

// --- Queries ---------------------------------------------------------------

const templateId = computed(() => (props.itemType === 'template' ? (props.itemId ?? '') : ''))
const mediaId = computed(() => (props.itemType === 'media' ? (props.itemId ?? '') : ''))
const deploymentId = computed(() => (props.itemType === 'deployment' ? (props.itemId ?? '') : ''))

const {
  data: templateAllowed,
  isPending: templateIsPending,
  error: templateError
} = useQuery({
  ...getTemplateAllowedOptions({ path: { template_id: templateId.value } }),
  queryKey: computed(() => getTemplateAllowedQueryKey({ path: { template_id: templateId.value } })),
  enabled: computed(() => props.open && !!templateId.value)
})

const {
  data: mediaAllowed,
  isPending: mediaIsPending,
  error: mediaError
} = useQuery({
  ...getMediaAllowedTableOptions({ path: { media_id: mediaId.value } }),
  queryKey: computed(() => getMediaAllowedTableQueryKey({ path: { media_id: mediaId.value } })),
  enabled: computed(() => props.open && !!mediaId.value)
})

const {
  data: deploymentAllowed,
  isPending: deploymentIsPending,
  error: deploymentError
} = useQuery({
  ...getDeploymentAllowedOptions({ path: { deployment_id: deploymentId.value } }),
  queryKey: computed(() =>
    getDeploymentAllowedQueryKey({ path: { deployment_id: deploymentId.value } })
  ),
  enabled: computed(() => props.open && !!deploymentId.value)
})

const categoryGroups = useQuery({
  ...getAvailableGroupsForCategoryOptions(),
  enabled: computed(() => props.open && !templateId.value && !mediaId.value && !deploymentId.value)
})

const allowedData = computed(() => {
  if (templateId.value) return templateAllowed.value
  if (mediaId.value) return mediaAllowed.value
  if (deploymentId.value) return deploymentAllowed.value
  return undefined
})

const allowedIsPending = computed(() => {
  if (templateId.value) return templateIsPending.value
  if (mediaId.value) return mediaIsPending.value
  if (deploymentId.value) return deploymentIsPending.value
  return categoryGroups.isPending.value
})

const allowedError = computed(() => {
  if (templateId.value) return templateError.value
  if (mediaId.value) return mediaError.value
  if (deploymentId.value) return deploymentError.value
  return categoryGroups.error.value
})

// --- Selection state -------------------------------------------------------

const selectedGroups = ref<string[]>([])
const selectedUsers = ref<string[]>([])
const apiAllGroups = ref(false)

const shareWithEveryone = ref(false)

const groupSearch = ref('')
const userSearch = ref('')
const userGroupFilter = ref<string[]>([])

const hydrated = ref(false)
const dirty = ref(false)
const summaryOpen = ref(false)

watch(
  () => props.open,
  (open) => {
    if (open) return

    hydrated.value = false
    dirty.value = false
    selectedGroups.value = []
    selectedUsers.value = []
    apiAllGroups.value = false
    shareWithEveryone.value = false
    groupSearch.value = ''
    userSearch.value = ''
    userGroupFilter.value = []
    summaryOpen.value = false
  }
)

// --- Groups column ---------------------------------------------------------

const expectsApiState = computed(
  () => !!templateId.value || !!mediaId.value || !!deploymentId.value
)

const rawGroups = computed(() => {
  const groups = expectsApiState.value
    ? allowedData.value?.available_groups
    : categoryGroups.data.value?.available_groups
  return Array.isArray(groups) ? groups : []
})

const availableGroups = computed<AllowedOption[]>(() =>
  rawGroups.value.map((group) => ({ value: group.id, label: group.name }))
)

const readBucket = (value: boolean | string[] | undefined, all: () => string[]): string[] => {
  if (!Array.isArray(value)) return []
  if (value.length === 0) return everyoneEnabled.value ? all() : []
  return [...value]
}

const hydrate = () => {
  if (expectsApiState.value && !allowedData.value) return
  const source = props.selection ?? allowedData.value?.selected
  if (!source) return

  const allGroupIds = () => availableGroups.value.map((group) => group.value)

  if (
    everyoneEnabled.value &&
    Array.isArray(source.groups) &&
    source.groups.length === 0 &&
    allGroupIds().length === 0
  ) {
    return
  }

  selectedGroups.value = readBucket(source.groups, allGroupIds)

  apiAllGroups.value =
    everyoneEnabled.value && Array.isArray(source.groups) && source.groups.length === 0
  shareWithEveryone.value =
    everyoneEnabled.value && Array.isArray(source.users) && source.users.length === 0
  selectedUsers.value =
    !shareWithEveryone.value && Array.isArray(source.users) ? [...source.users] : []
  summaryOpen.value =
    selectedGroups.value.length > 0 || selectedUsers.value.length > 0 || apiAllGroups.value
  hydrated.value = true
}

watch(
  [() => props.open, () => props.selection, allowedData, availableGroups],
  () => {
    if (props.open && !hydrated.value) hydrate()
  },
  { immediate: true }
)

const groupsEmptyText = computed(() =>
  allowedError.value ? t('api.loading-error') : t('components.allowed-modal.empty.groups')
)

// Counted against availableGroups so it always matches what the column considers selected.
const selectedGroupCount = computed(() => {
  const selected = new Set(selectedGroups.value)
  return availableGroups.value.filter((group) => selected.has(group.value)).length
})

// --- Users column ----------------------------------------------------------

const userTerm = computed(() => userSearch.value.trim())
const debouncedUserTerm = refDebounced(userTerm, 250)

const USERS_LIMIT = 200

const usersQuery = computed(() => ({
  search: debouncedUserTerm.value,
  limit: USERS_LIMIT,
  ...roleQuery.value,
  ...(userGroupFilter.value.length ? { groups: [...userGroupFilter.value] } : {})
}))

const categoryUsers = useQuery({
  ...searchUsersInCategoryOptions({ query: usersQuery.value }),
  queryKey: computed(() => searchUsersInCategoryQueryKey({ query: usersQuery.value })),
  enabled: computed(() => props.open),
  placeholderData: keepPreviousData
})

const groupNames = computed(
  () => new Map(availableGroups.value.map((group) => [group.value, group.label]))
)

const toOption = (user: AvailableUser, subLabel?: string): AllowedOption => ({
  value: user.id,
  label: user.name || user.username,
  subLabel,
  avatar: user.photo ?? ''
})

const categoryUserOptions = computed<AllowedOption[]>(() =>
  (categoryUsers.data.value?.users ?? []).map((user) =>
    toOption(user, groupNames.value.get(user.group ?? ''))
  )
)

const usersColumnItems = computed<AllowedOption[]>(() => {
  if (!props.preselectedUsers || userTerm.value || userGroupFilter.value.length) {
    return categoryUserOptions.value
  }

  const fetched = new Map(categoryUserOptions.value.map((user) => [user.value, user]))
  const preselected = props.preselectedUsers.map((user) => fetched.get(user.value) ?? user)
  const preselectedIds = new Set(preselected.map((user) => user.value))
  return [
    ...preselected,
    ...categoryUserOptions.value.filter((user) => !preselectedIds.has(user.value))
  ]
})

const usersLoading = computed(() => categoryUsers.isPending.value)

const searchSettled = computed(() => debouncedUserTerm.value === userTerm.value)

const usersFooterText = computed(() => {
  if (categoryUsers.isFetching.value || !searchSettled.value) return ''
  const shown = categoryUserOptions.value.length
  const total = categoryUsers.data.value?.total ?? 0
  if (shown === 0 || total <= shown) return ''
  return t('components.allowed-modal.search.user.truncated', { shown, total })
})

const userSearchPlaceholder = computed(() =>
  userGroupFilter.value.length
    ? t('components.allowed-modal.search.user.filtered-placeholder')
    : t('components.allowed-modal.search.user.placeholder')
)

const usersEmptyText = computed(() => {
  if (categoryUsers.error.value) return t('api.loading-error')
  if (userTerm.value || userGroupFilter.value.length) {
    return t('components.allowed-modal.search.user.empty')
  }
  return t('components.allowed-modal.empty.no-users')
})

// --- Selection summary ---------------------------------------------------

const knownUsers = ref(new Map<string, AllowedOption>())
const knownUserGroups = ref(new Map<string, string>())

const remember = (options: AllowedOption[] | undefined) => {
  for (const option of options ?? []) knownUsers.value.set(option.value, option)
}

const rememberGroups = (users: AvailableUser[] | undefined) => {
  for (const user of users ?? []) {
    if (user.group) knownUserGroups.value.set(user.id, user.group)
  }
}

watch(
  () => allowedData.value?.selected_users,
  (users) => {
    remember(users?.map((user) => toOption(user, user.username)))
    rememberGroups(users)
  },
  { immediate: true }
)
watch(categoryUserOptions, (options) => remember(options), { immediate: true })
watch(
  () => categoryUsers.data.value?.users,
  (users) => rememberGroups(users),
  { immediate: true }
)
watch(
  () => props.preselectedUsers,
  (users) => remember(users),
  { immediate: true }
)

const summaryGroups = computed(() => {
  const selected = new Set(selectedGroups.value)
  return availableGroups.value.filter((group) => selected.has(group.value))
})

const summaryUsers = computed<AllowedOption[]>(() =>
  selectedUsers.value.map(
    (id) =>
      knownUsers.value.get(id) ?? {
        value: id,
        label: t('components.allowed-modal.summary.unknown-user')
      }
  )
)

// --- Groups column options ------------------------------------------------

const selectedUsersByGroup = computed(() => {
  const counts = new Map<string, number>()
  for (const userId of selectedUsers.value) {
    const groupId = knownUserGroups.value.get(userId)
    if (groupId) counts.set(groupId, (counts.get(groupId) ?? 0) + 1)
  }
  return counts
})

const groupOptions = computed<AllowedOption[]>(() => {
  const selected = new Set(selectedGroups.value)
  return rawGroups.value.map((group) => {
    const total = group.users_count ?? 0
    const picked = selected.has(group.id) ? 0 : (selectedUsersByGroup.value.get(group.id) ?? 0)
    return {
      value: group.id,
      label: group.name,
      subLabel:
        picked > 0
          ? t('components.allowed-modal.group-users-partial', { selected: picked, total })
          : t('users.count.users', total)
    }
  })
})

// --- Handlers --------------------------------------------------------------

const dropMembersOf = (groupIds: string[]) => {
  const groups = new Set(groupIds)
  selectedUsers.value = selectedUsers.value.filter((userId) => {
    const groupId = knownUserGroups.value.get(userId)
    return !groupId || !groups.has(groupId)
  })
}

const toggleAllGroups = (selectAll: boolean) => {
  if (props.usersOnly) return
  dirty.value = true
  const groupIds = availableGroups.value.map((group) => group.value)
  apiAllGroups.value = everyoneEnabled.value && selectAll
  selectedGroups.value = selectAll ? groupIds : []
  if (selectAll) dropMembersOf(groupIds)
}

const toggleGroup = (groupId: string) => {
  if (props.usersOnly) return
  dirty.value = true
  apiAllGroups.value = false
  const adding = !selectedGroups.value.includes(groupId)
  selectedGroups.value = adding
    ? [...selectedGroups.value, groupId]
    : selectedGroups.value.filter((id) => id !== groupId)
  if (adding) dropMembersOf([groupId])
}

const toggleUser = (userId: string) => {
  dirty.value = true
  selectedUsers.value = selectedUsers.value.includes(userId)
    ? selectedUsers.value.filter((id) => id !== userId)
    : [...selectedUsers.value, userId]
}

const removeUser = (userId: string) => {
  dirty.value = true
  selectedUsers.value = selectedUsers.value.filter((id) => id !== userId)
}

const setShareWithEveryone = (value: boolean) => {
  if (props.loading || props.readonly) return
  dirty.value = true
  shareWithEveryone.value = value
}

const isEmptySelection = computed(() => {
  if (props.usersOnly) return selectedUsers.value.length === 0
  return (
    !shareWithEveryone.value &&
    !apiAllGroups.value &&
    selectedGroups.value.length === 0 &&
    selectedUsers.value.length === 0
  )
})

const requireSelectionText = computed(() =>
  props.usersOnly
    ? t('components.allowed-modal.require-selection-users')
    : t('components.allowed-modal.require-selection')
)

const columnsDisabled = computed(() => props.loading || props.readonly)

const saveDisabled = computed(
  () => props.loading || !dirty.value || (props.requireSelection && isEmptySelection.value)
)

const saveHint = computed(() =>
  !props.loading && !dirty.value ? t('components.allowed-modal.no-changes') : ''
)

const handleSave = () => {
  if (saveDisabled.value) return
  emit('save', {
    groups: props.usersOnly
      ? false
      : shareWithEveryone.value
        ? false
        : apiAllGroups.value
          ? []
          : selectedGroups.value.length
            ? [...selectedGroups.value]
            : false,
    users: shareWithEveryone.value
      ? []
      : selectedUsers.value.length
        ? [...selectedUsers.value]
        : false
  })
}

const handleClose = () => {
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="props.title || t('components.allowed-modal.title')"
    :description="
      props.description ||
      t(
        `components.allowed-modal.description.${props.itemType}`,
        t('components.allowed-modal.description.generic')
      )
    "
    size="4xl"
    :close-on-backdrop-click="false"
    @close="handleClose"
  >
    <div v-if="props.warning" class="mb-4 w-full flex justify-center">
      <Alert variant="warning" class="w-[min(100%,var(--spacing-256))]">
        <FeaturedIconOutline kind="outline" color="warning" />
        <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
          t('components.allowed-modal.warning')
        }}</AlertTitle>
        <AlertDescription>{{ props.warning }}</AlertDescription>
      </Alert>
    </div>
    <AllowedModalSummary
      v-if="!shareWithEveryone"
      v-model:open="summaryOpen"
      :groups="summaryGroups"
      :users="summaryUsers"
      :all-groups="apiAllGroups"
      :show-groups="!props.usersOnly"
      :disabled="columnsDisabled"
      @remove-group="toggleGroup"
      @remove-user="removeUser"
      @remove-all-groups="toggleAllGroups(false)"
    />
    <Alert v-else class="mb-4 shrink-0" data-slot="share-everyone-alert">
      <div class="flex flex-row items-center gap-2">
        <FeaturedIconOutline kind="filled" color="brand" name="users-02" />
        <div class="flex min-w-0 flex-col">
          <AlertTitle class="font-semibold text-gray-warm-700">
            {{ t('components.allowed-modal.share-everyone.alert.title') }}
          </AlertTitle>
          <AlertDescription class="text-gray-warm-600">
            {{ t('components.allowed-modal.share-everyone.alert.description') }}
          </AlertDescription>
        </div>
      </div>
    </Alert>

    <Field v-if="everyoneEnabled" orientation="horizontal" class="mb-4">
      <Switch
        id="share-everyone"
        :model-value="shareWithEveryone"
        :disabled="props.loading || props.readonly"
        data-slot="share-everyone-switch"
        @update:model-value="setShareWithEveryone"
      />
      <FieldContent>
        <FieldLabel for="share-everyone">
          {{ t('components.allowed-modal.share-everyone.label') }}
        </FieldLabel>
      </FieldContent>
    </Field>

    <div v-if="!shareWithEveryone" class="flex h-[60vh] max-h-[480px] min-h-[320px] gap-6">
      <AllowedModalColumn
        v-if="!props.usersOnly"
        v-model:search="groupSearch"
        :title="t('components.allowed-modal.columns.groups')"
        :items="groupOptions"
        :selected="selectedGroups"
        :loading="allowedIsPending"
        :disabled="columnsDisabled"
        :search-placeholder="t('components.allowed-modal.search.group.placeholder')"
        :empty-text="groupsEmptyText"
        :not-found-text="t('components.allowed-modal.search.group.empty')"
        :select-all="everyoneEnabled"
        :select-all-checked="apiAllGroups"
        :select-all-label="t('components.allowed-modal.select-all.groups')"
        :select-all-count-label="
          t('components.allowed-modal.select-all.count', {
            selected: selectedGroupCount,
            total: availableGroups.length
          })
        "
        @toggle="toggleGroup"
        @toggle-all="toggleAllGroups"
      />

      <AllowedModalColumn
        v-model:search="userSearch"
        :title="t('components.allowed-modal.columns.users')"
        :items="usersColumnItems"
        :selected="selectedUsers"
        :loading="usersLoading"
        :disabled="columnsDisabled"
        :search-placeholder="userSearchPlaceholder"
        :empty-text="usersEmptyText"
        :not-found-text="t('components.allowed-modal.search.user.empty')"
        :footer-text="usersFooterText"
        :filter-locally="false"
        @toggle="toggleUser"
      >
        <template #search-actions>
          <AllowedModalGroupFilter
            v-model="userGroupFilter"
            :options="availableGroups"
            :disabled="columnsDisabled"
          />
        </template>
      </AllowedModalColumn>
    </div>

    <div v-if="props.error" class="mt-4 w-full flex justify-center">
      <Alert variant="destructive" class="w-[min(100%,var(--spacing-256))]">
        <AlertDescription>{{ props.error }}</AlertDescription>
      </Alert>
    </div>

    <template #footer>
      <div class="flex w-full items-center justify-end gap-4">
        <p
          v-if="props.requireSelection && isEmptySelection"
          class="min-w-0 truncate text-sm text-gray-warm-600"
        >
          {{ requireSelectionText }}
        </p>
        <div class="flex shrink-0 gap-2">
          <Button hierarchy="secondary-gray" :disabled="props.loading" @click="handleClose">
            {{ t('components.allowed-modal.cancel') }}
          </Button>
          <Tooltip v-if="!props.readonly" :disabled="!saveHint">
            <TooltipTrigger as-child>
              <span class="flex">
                <Button
                  :disabled="saveDisabled"
                  :icon="props.loading ? 'loading-02' : ''"
                  icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
                  :class="saveDisabled && 'pointer-events-none'"
                  @click="handleSave"
                >
                  {{ t('components.allowed-modal.save') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent v-if="saveHint" :title="saveHint" />
          </Tooltip>
        </div>
      </div>
    </template>
  </Modal>
</template>
