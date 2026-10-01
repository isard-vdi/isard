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
  getTemplateAllowedQueryKey,
  getUsersInGroupOptions,
  getUsersInGroupQueryKey
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
const apiIndeterminateGroups = ref<string[]>([])
const apiAllGroups = ref(false)

const shareWithEveryone = ref(false)
const usersByGroup = ref<Record<string, AllowedOption[]>>({})

const viewedGroup = ref<string | null>(null)
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
    apiIndeterminateGroups.value = []
    apiAllGroups.value = false
    shareWithEveryone.value = false
    viewedGroup.value = null
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

const availableGroups = computed<AllowedOption[]>(() => {
  const groups = expectsApiState.value
    ? allowedData.value?.available_groups
    : categoryGroups.data.value?.available_groups
  if (!Array.isArray(groups)) return []
  return groups.map((group) => ({
    value: group.id,
    label: group.name,
    subLabel: group.description ?? undefined
  }))
})

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
  apiIndeterminateGroups.value = Array.isArray(allowedData.value?.indeterminate_groups)
    ? allowedData.value.indeterminate_groups.map((group) => group.id)
    : []
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

const indeterminateGroups = computed(() => {
  const ids = new Set(apiIndeterminateGroups.value)

  for (const [groupId, members] of Object.entries(usersByGroup.value)) {
    if (members.some((member) => selectedUsers.value.includes(member.value))) {
      ids.add(groupId)
    } else {
      ids.delete(groupId)
    }
  }
  for (const groupId of selectedGroups.value) ids.delete(groupId)
  return [...ids]
})

const groupsEmptyText = computed(() =>
  allowedError.value ? t('api.loading-error') : t('components.allowed-modal.empty.groups')
)

// Counted against availableGroups so it always matches what the column considers selected.
const selectedGroupCount = computed(() => {
  const selected = new Set(selectedGroups.value)
  return availableGroups.value.filter((group) => selected.has(group.value)).length
})

// --- Users column ----------------------------------------------------------

const usersInGroup = useQuery({
  ...getUsersInGroupOptions({
    path: { group_id: viewedGroup.value ?? '' },
    query: roleQuery.value
  }),
  queryKey: computed(() =>
    getUsersInGroupQueryKey({
      path: { group_id: viewedGroup.value ?? '' },
      query: roleQuery.value
    })
  ),
  enabled: computed(() => props.open && !!viewedGroup.value)
})

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
  enabled: computed(() => props.open && !viewedGroup.value),
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

watch(
  () => usersInGroup.data.value,
  (data) => {
    const groupId = viewedGroup.value
    if (!groupId || !Array.isArray(data?.users)) return
    usersByGroup.value = {
      ...usersByGroup.value,
      [groupId]: data.users.map((user) => toOption(user, user.username))
    }
  },
  { immediate: true }
)

const viewedGroupUsers = computed<AllowedOption[]>(() =>
  viewedGroup.value ? (usersByGroup.value[viewedGroup.value] ?? []) : []
)

const viewedGroupName = computed(
  () => availableGroups.value.find((group) => group.value === viewedGroup.value)?.label ?? ''
)

const checkedUsers = computed(() => {
  if (viewedGroup.value && selectedGroups.value.includes(viewedGroup.value)) {
    return viewedGroupUsers.value.map((user) => user.value)
  }
  return selectedUsers.value
})

const usersColumnItems = computed<AllowedOption[]>(() => {
  if (viewedGroup.value) return viewedGroupUsers.value
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

const usersLoading = computed(() => {
  if (viewedGroup.value) {
    return usersInGroup.isPending.value && viewedGroupUsers.value.length === 0
  }
  return categoryUsers.isPending.value
})

const searchSettled = computed(() => debouncedUserTerm.value === userTerm.value)

const usersFooterText = computed(() => {
  if (viewedGroup.value || categoryUsers.isFetching.value || !searchSettled.value) return ''
  const shown = categoryUserOptions.value.length
  const total = categoryUsers.data.value?.total ?? 0
  if (shown === 0 || total <= shown) return ''
  return t('components.allowed-modal.search.user.truncated', { shown, total })
})

const usersColumnTitle = computed(() =>
  viewedGroup.value
    ? t('components.allowed-modal.columns.users-in-group', { group_name: viewedGroupName.value })
    : t('components.allowed-modal.columns.users')
)

const userSearchPlaceholder = computed(() =>
  viewedGroup.value
    ? t('components.allowed-modal.search.user-in-group.placeholder', {
        group_name: viewedGroupName.value
      })
    : userGroupFilter.value.length
      ? t('components.allowed-modal.search.user.filtered-placeholder')
      : t('components.allowed-modal.search.user.placeholder')
)

const usersEmptyText = computed(() => {
  if (viewedGroup.value) {
    if (usersInGroup.error.value) return t('api.loading-error')
    return t('components.allowed-modal.empty.users')
  }
  if (categoryUsers.error.value) return t('api.loading-error')
  if (userTerm.value || userGroupFilter.value.length) {
    return t('components.allowed-modal.search.user.empty')
  }
  return t('components.allowed-modal.empty.no-users')
})

// --- Selection summary ---------------------------------------------------

const knownUsers = ref(new Map<string, AllowedOption>())

const remember = (options: AllowedOption[] | undefined) => {
  for (const option of options ?? []) knownUsers.value.set(option.value, option)
}

watch(
  () => allowedData.value?.selected_users,
  (users) => remember(users?.map((user) => toOption(user, user.username))),
  { immediate: true }
)
watch(categoryUserOptions, (options) => remember(options), { immediate: true })
watch(
  usersByGroup,
  (groups) => {
    for (const members of Object.values(groups)) remember(members)
  },
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

// --- Handlers --------------------------------------------------------------

const viewGroup = (groupId: string) => {
  viewedGroup.value = viewedGroup.value === groupId ? null : groupId
  userSearch.value = ''
}

const dropKnownMembers = (groupIds: string[]) => {
  const memberIds = new Set(
    groupIds.flatMap((id) => (usersByGroup.value[id] ?? []).map((member) => member.value))
  )
  if (memberIds.size === 0) return
  selectedUsers.value = selectedUsers.value.filter((id) => !memberIds.has(id))
}

const toggleAllGroups = (selectAll: boolean) => {
  if (props.usersOnly) return
  dirty.value = true
  const groupIds = availableGroups.value.map((group) => group.value)
  apiAllGroups.value = everyoneEnabled.value && selectAll
  selectedGroups.value = selectAll ? groupIds : []
  dropKnownMembers(groupIds)
}

const toggleGroup = (groupId: string) => {
  if (props.usersOnly) return
  dirty.value = true
  apiAllGroups.value = false
  selectedGroups.value = selectedGroups.value.includes(groupId)
    ? selectedGroups.value.filter((id) => id !== groupId)
    : [...selectedGroups.value, groupId]
  dropKnownMembers([groupId])
}

const toggleUser = (userId: string) => {
  dirty.value = true
  const groupId = viewedGroup.value

  if (!groupId) {
    selectedUsers.value = selectedUsers.value.includes(userId)
      ? selectedUsers.value.filter((id) => id !== userId)
      : [...selectedUsers.value, userId]
    return
  }

  const users = [...selectedUsers.value]
  if (selectedGroups.value.includes(groupId)) {
    apiAllGroups.value = false
    selectedGroups.value = selectedGroups.value.filter((id) => id !== groupId)
    for (const member of viewedGroupUsers.value) {
      if (!users.includes(member.value)) users.push(member.value)
    }
  }

  selectedUsers.value = users.includes(userId)
    ? users.filter((id) => id !== userId)
    : [...users, userId]
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
        v-model:search="groupSearch"
        :title="t('components.allowed-modal.columns.groups')"
        :items="availableGroups"
        :selected="selectedGroups"
        :indeterminate="indeterminateGroups"
        :active-id="viewedGroup"
        :loading="allowedIsPending"
        :disabled="columnsDisabled"
        :search-placeholder="t('components.allowed-modal.search.group.placeholder')"
        :empty-text="groupsEmptyText"
        :not-found-text="t('components.allowed-modal.search.group.empty')"
        :selectable="!props.usersOnly"
        activatable
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
        @select="viewGroup"
      />

      <AllowedModalColumn
        v-model:search="userSearch"
        :title="usersColumnTitle"
        :items="usersColumnItems"
        :selected="checkedUsers"
        :loading="usersLoading"
        :disabled="columnsDisabled"
        :search-placeholder="userSearchPlaceholder"
        :empty-text="usersEmptyText"
        :not-found-text="t('components.allowed-modal.search.user.empty')"
        :footer-text="usersFooterText"
        :filter-locally="!!viewedGroup"
        @toggle="toggleUser"
      >
        <template v-if="!viewedGroup" #search-actions>
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
