<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserMigrationStore, type MigrationKindState } from '@/stores/user-migration'
import { describeApiErrors } from '@/lib/api-errors'
import { SinglePageLayout } from '@/layouts/single-page'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { MigrationItemChip, MigrationItemTable } from '@/components/migration'
import { Skeleton } from '@/components/ui/skeleton'
import { migrationMigrateUser } from '@/gen/oas/apiv4'

import { useQuery } from '@tanstack/vue-query'

import { useForm, type AnyFieldApi } from '@tanstack/vue-form'
import * as z from 'zod'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { Field, FieldError, FieldLabel, FieldContent } from '@/components/ui/field'

import {
  getUserDetailsOptions,
  migrationListItemsOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
const { t, te } = useI18n()

const {
  isPending: userMigrationItemsIsPending,
  isError: userMigrationItemsIsError,
  error: userMigrationItemsError,
  data: userMigrationItems
} = useQuery({
  ...migrationListItemsOptions(),
  retry: false
})

// TODO: provider data should be unified in the authentication OAS definition
const {
  isPending: getUserIsPending,
  isError: getUserIsError,
  error: getUserError, // TODO: handle this error
  data: getUser
} = useQuery(getUserDetailsOptions())

const isPending = computed(() => userMigrationItemsIsPending.value || getUserIsPending.value)
const isError = computed(() => userMigrationItemsIsError.value || getUserIsError.value)
const error = computed(() => userMigrationItemsError.value)

// TODO: Type this!
type UserMigrationItemsError = string | 'unknown'

// const isUserMigrationItemsError = (error: string): error is UserMigrationItemsError => {
//   switch (error) {
//     case 'unknown':
//     case 'invalid_token':
//     case 'same_user_migration':
//     case 'different_category_migration':
//     case 'role_migration_admin':
//     case 'role_migration_user':
//     case 'migration_desktop_quota_error':
//     case 'migration_template_quota_error':
//     case 'migration_media_quota_error':
//     case 'migration_deployments_quota_error':
//       return true

//     default:
//       return false
//   }
// }

const userMigrationItemsErrorMsgs = computed<string[] | undefined>(() =>
  isError.value && userMigrationItemsError.value
    ? describeApiErrors(userMigrationItemsError.value, { t, te }, 'user_migration')
    : undefined
)

/*
 * View logic
 */
type MigrationItemKind = 'desktops' | 'templates' | 'media' | 'deployments'

const itemsKind = ref<
  {
    title: string
    key: MigrationItemKind
    count: number
    colorClass: string
    icon: string
  }[]
>([
  {
    title: 'Desktops',
    key: 'desktops',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'monitor-02'
  },
  {
    title: 'Templates',
    key: 'templates',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'colors'
  },
  {
    title: 'Media',
    key: 'media',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'disc-02'
  },
  {
    title: 'Deployments',
    key: 'deployments',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'layout-alt-04'
  }
])

// Item types that actually have items, used to render the selectable chips.
const availableKinds = computed(() =>
  itemsKind.value.filter((item) => (userMigrationItems.value?.[item.key].length ?? 0) > 0)
)

// Selected chip; defaults to the first available type until the user picks one.
const selectedKind = ref<MigrationItemKind | null>(null)
const activeKind = computed<MigrationItemKind | null>(
  () => selectedKind.value ?? availableKinds.value[0]?.key ?? null
)
const activeItems = computed(() =>
  activeKind.value ? (userMigrationItems.value?.[activeKind.value] ?? []) : []
)

/*
 * Actions
 */
const formSchema = z.object({
  accept: z.boolean().refine((val) => val === true, {
    message: t('views.migration.form.accept.required')
  })
})

const migrationSubmitted = ref(false)
const migrationSuccess = ref(false)
const userMigrationError = ref<string[]>([])

// Import runs in the background after migrate-user returns; progress arrives
// over the `user_migration_data` websocket event (see stores/user-migration).
const migrationStore = useUserMigrationStore()

const migrationInProgress = computed(
  () => migrationSubmitted.value && !migrationSuccess.value && userMigrationError.value.length === 0
)

const progressKinds = computed(() =>
  itemsKind.value
    .filter((item) => (userMigrationItems.value?.[item.key].length ?? 0) > 0)
    .map((item) => ({ ...item, state: migrationStore.kindState(item.key) }))
)

const stateIcon = (state: MigrationKindState) =>
  ({
    pending: 'clock',
    in_progress: 'loading-01',
    done: 'check-circle',
    error: 'alert-circle'
  })[state]

const stateColor = (state: MigrationKindState) =>
  ({
    pending: 'gray-warm-400',
    in_progress: 'brand-600',
    done: 'success-600',
    error: 'error-600'
  })[state]

// Each resource type is reported as done/not by the backend, so a kind's bar
// is 0 until it completes (or errors), then 100.
const kindPercent = (state: MigrationKindState) => (state === 'done' || state === 'error' ? 100 : 0)

// Overall progress = share of resource types that have finished.
const migrationPercent = computed(() => {
  const kinds = progressKinds.value
  if (kinds.length === 0) return migrationStore.isDone ? 100 : 0
  const finished = kinds.filter((k) => k.state === 'done' || k.state === 'error').length
  return Math.round((finished / kinds.length) * 100)
})

// The websocket drives the final outcome: the migrate-user response only
// confirms the background task started, not that the import finished.
watch(
  () => migrationStore.isDone,
  (done) => {
    if (done) migrationSuccess.value = true
  }
)
watch(
  () => migrationStore.isFailed,
  (failed) => {
    if (!failed) return
    const codes = (['desktops', 'templates', 'media', 'deployments'] as const)
      .map((kind) => migrationStore.progress?.[`migrated_${kind}_error`])
      .filter((code): code is string => typeof code === 'string' && code.length > 0)
    userMigrationError.value = describeApiErrors(
      { errors: codes.map((code) => ({ description_code: code })) },
      { t, te },
      'user_migration'
    )
  }
)

onUnmounted(() => migrationStore.$reset())

const form = useForm({
  defaultValues: {
    accept: false
  },
  validators: {
    onSubmit: formSchema
  },
  onSubmit: async () => {
    // Prevent multiple submissions
    if (migrationSubmitted.value === true) {
      return
    }
    migrationStore.$reset()
    migrationSubmitted.value = true

    const { error } = await migrationMigrateUser()

    if (error !== undefined) {
      userMigrationError.value = describeApiErrors(error, { t, te }, 'user_migration')
    }
    // Success is confirmed by the `user_migration_data` websocket (status
    // === 'migrated'); see the watcher above.
  }
})

const isInvalid = (field: AnyFieldApi) => field.state.meta.isTouched && !field.state.meta.isValid

const goToDesktops = () => {
  window.location.pathname = '/desktops'
}

const itemQuotaExceeded = (item: string) => {
  switch (item) {
    case 'desktops':
      return userMigrationItems.value?.quota_errors?.some(
        (error) => error.description_code === 'migration_desktop_quota_error'
      )
    case 'templates':
      return userMigrationItems.value?.quota_errors?.some(
        (error) => error.description_code === 'migration_template_quota_error'
      )
    case 'media':
      return userMigrationItems.value?.quota_errors?.some(
        (error) => error.description_code === 'migration_media_quota_error'
      )
    case 'deployments':
      return userMigrationItems.value?.quota_errors?.some(
        (error) => error.description_code === 'migration_deployments_quota_error'
      )
    default:
      return false
  }
}
</script>

<template>
  <SinglePageLayout :go-back="true">
    <template #title>
      <h1 class="mt-[46px] text-center text-display-md font-bold text-brand-700">
        {{ t('views.migration.title') }}
      </h1>
      <div
        v-if="isPending"
        class="mb-[32px] w-full flex flex-col gap-2 items-center justify-center"
      >
        <Skeleton class="h-4 w-1/3" />
      </div>
      <h2
        v-else-if="userMigrationItems"
        class="mb-[32px] text-center text-md font-semibold text-gray-warm-800"
      >
        {{
          t('views.migration.subtitle', {
            old_user_name: userMigrationItems?.users[0].name,
            old_user_provider: userMigrationItems?.users[0].provider,
            new_user_name: getUser?.name,
            new_user_provider: getUser?.provider
          })
        }}
      </h2>
    </template>
    <template #main>
      <img
        v-if="!(userMigrationItemsIsError && userMigrationItemsErrorMsgs)"
        src="@/assets/img/HELLO.svg"
        class="fixed bottom-0 left-0 -z-10 h-1/2 invisible md:visible"
      />

      <div v-if="isPending" class="w-full flex flex-col gap-2 items-center justify-center">
        <Skeleton class="h-6 w-1/2" />
        <div class="flex flex-row w-1/2 gap-2 my-4">
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
        </div>
        <Skeleton class="h-6 w-1/6" />
      </div>

      <div
        v-else-if="userMigrationItemsIsError && userMigrationItemsErrorMsgs"
        class="flex justify-center"
      >
        <Alert variant="destructive" class="w-full max-w-2xl">
          <Icon name="alert-octagon" class="h-5 w-5" stroke-color="error-600" />
          <AlertTitle class="font-semibold text-error-800">
            {{ t('views.migration.error.title') }}
          </AlertTitle>
          <AlertDescription class="text-error-700">
            <ul class="mt-1 list-disc space-y-1 pl-4">
              <li v-for="msg in userMigrationItemsErrorMsgs" :key="msg">{{ msg }}</li>
            </ul>
          </AlertDescription>
        </Alert>
      </div>

      <div v-else-if="migrationSuccess" class="flex justify-center">
        <Alert class="w-full max-w-2xl border-success-200 bg-success-25">
          <Icon name="check-circle" class="h-5 w-5" stroke-color="success-600" />
          <AlertTitle class="text-lg font-semibold text-gray-warm-800">
            {{ t('views.migration.success.title') }}
          </AlertTitle>
          <AlertDescription class="flex flex-col gap-4 text-gray-warm-700">
            <p>{{ t('views.migration.success.description') }}</p>
            <div class="flex justify-end">
              <Button class="px-8" @click="goToDesktops">
                {{ t('views.migration.success.button') }}
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </div>

      <div v-else-if="userMigrationError.length > 0" class="flex justify-center">
        <Alert variant="destructive" class="w-full max-w-2xl">
          <Icon name="alert-octagon" class="h-5 w-5" stroke-color="error-600" />
          <AlertTitle class="font-semibold text-error-800">
            {{ t('views.migration.error.title') }}
          </AlertTitle>
          <AlertDescription class="text-error-700">
            <ul class="mt-1 list-disc space-y-1 pl-4">
              <li v-for="msg in userMigrationError" :key="msg">{{ msg }}</li>
            </ul>
          </AlertDescription>
        </Alert>
      </div>

      <div v-else-if="migrationInProgress" class="flex justify-center">
        <Alert class="w-full max-w-2xl">
          <Icon name="loading-01" class="h-5 w-5 animate-spin" stroke-color="brand-600" />
          <AlertTitle class="text-lg font-semibold text-gray-warm-800">
            {{ t('views.migration.progress.title') }}
          </AlertTitle>
          <AlertDescription class="flex flex-col gap-6 text-gray-warm-700">
            <p>{{ t('views.migration.progress.description') }}</p>

            <!-- Overall progress -->
            <div class="flex flex-col gap-2">
              <div class="flex flex-row items-center justify-between text-sm">
                <span>{{ t('views.migration.progress.overall') }}</span>
                <span class="font-semibold text-gray-warm-800">{{ migrationPercent }}%</span>
              </div>
              <Progress :model-value="migrationPercent" class="h-2" />
            </div>

            <!-- Per resource-type progress -->
            <ul class="flex flex-col gap-4">
              <li v-for="item in progressKinds" :key="item.key" class="flex flex-col gap-1.5">
                <div class="flex flex-row items-center gap-2 text-sm">
                  <Icon
                    :name="stateIcon(item.state)"
                    class="h-4 w-4"
                    :class="item.state === 'in_progress' ? 'animate-spin' : ''"
                    :stroke-color="stateColor(item.state)"
                  />
                  <span class="font-medium text-gray-warm-800">
                    {{ t(`domains.capitalized.${item.key}`, 2) }}
                  </span>
                  <span class="text-gray-warm-500">
                    ({{ userMigrationItems?.[item.key].length }})
                  </span>
                </div>
                <Progress
                  :model-value="kindPercent(item.state)"
                  class="h-2"
                  :class="item.state === 'error' ? 'text-error-600' : ''"
                />
              </li>
            </ul>
          </AlertDescription>
        </Alert>
      </div>

      <div
        v-else-if="userMigrationItems"
        class="mx-auto mb-[32px] flex w-full max-w-3xl flex-col items-center gap-6"
      >
        <!-- Type selector chips -->
        <div class="flex w-full flex-row flex-wrap items-center justify-center gap-3">
          <MigrationItemChip
            v-for="item in availableKinds"
            :key="item.key"
            :title="t(`domains.capitalized.${item.key}`, 2)"
            :count="userMigrationItems[item.key].length"
            :icon="item.icon"
            :warning="itemQuotaExceeded(item.key)"
            :active="activeKind === item.key"
            @click="selectedKind = item.key"
          />
        </div>

        <!-- Single panel for the selected type -->
        <MigrationItemTable
          v-if="activeKind"
          class="w-full"
          :title="t(`domains.capitalized.${activeKind}`, 2)"
          :icon="availableKinds.find((k) => k.key === activeKind)?.icon"
          :items="activeItems"
        />

        <div class="flex w-full justify-center">
          <Alert class="w-full max-w-2xl border-warning-200 bg-warning-25">
            <Icon name="alert-triangle" class="h-5 w-5" stroke-color="warning-600" />
            <AlertTitle class="text-md font-semibold text-warning-800">
              {{ t('views.migration.notification.title') }}
            </AlertTitle>
            <AlertDescription class="text-gray-warm-700">
              <p
                v-if="userMigrationItems?.action_after_migrate === 'delete'"
                class="font-semibold text-warning-800"
              >
                {{
                  t('views.migration.notification.description.delete_user', {
                    old_user_name: userMigrationItems?.users[0].name,
                    old_user_provider: userMigrationItems?.users[0].provider
                  })
                }}
              </p>
              <p
                v-else-if="userMigrationItems?.action_after_migrate === 'disable'"
                class="font-semibold text-warning-800"
              >
                {{
                  t('views.migration.notification.description.disable_user', {
                    old_user_name: userMigrationItems?.users[0].name,
                    old_user_provider: userMigrationItems?.users[0].provider
                  })
                }}
              </p>
              <p class="mt-1 whitespace-pre-line">
                {{ t('views.migration.notification.description.description') }}
              </p>
              <p class="mt-2 font-semibold text-gray-warm-800">
                {{ t('views.migration.notification.description.footer') }}
              </p>
            </AlertDescription>
          </Alert>
        </div>

        <!-- Button to confirm the migration -->
        <form
          class="flex flex-row items-start justify-center gap-8"
          @submit.prevent="form.handleSubmit"
        >
          <form.Field v-slot="{ field }" name="accept">
            <Field orientation="horizontal" :data-invalid="isInvalid(field)">
              <Checkbox
                :id="field.name"
                :name="field.name"
                :aria-invalid="isInvalid(field)"
                :model-value="field.state.value"
                @update:model-value="field.handleChange($event === true)"
              />
              <FieldContent class="ml-2">
                <FieldLabel :for="field.name">
                  {{ t('views.migration.form.accept.title') }}
                </FieldLabel>
                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </FieldContent>
            </Field>
          </form.Field>

          <Button
            type="submit"
            hierarchy="primary"
            size="lg"
            :disabled="isPending || migrationSubmitted"
          >
            {{ t('views.migration.form.submit') }}
          </Button>
        </form>
      </div>
    </template>
  </SinglePageLayout>
</template>
