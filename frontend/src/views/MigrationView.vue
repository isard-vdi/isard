<script setup lang="ts">
import { computed, ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { MigrationLayout } from '@/layouts/migration'
import MigrationError from '@/components/migration/MigrationError.vue'
import MigrationItemBox from '@/components/migration/MigrationItemBox.vue'
import MigrationItemTable from '@/components/migration/MigrationItemTable.vue'
import MigrationNotification from '@/components/migration/MigrationNotification.vue'
import CardBox from '@/components/card-box/CardBox.vue'
import Tooltip from '@/components/ui/tooltip/Tooltip.vue'
import Button from '@/components/ui/button/Button.vue'
import { Skeleton } from '@/components/ui/skeleton'
import {
  postUserMigrationAuto,
  type GetUserMigrationItemsResponse,
  type PostUserMigrationAutoError as ApiUserMigrationError
} from '@/gen/oas/api'

import { useQuery, useQueryClient } from '@tanstack/vue-query'

import {
  getUserMigrationItemsOptions,
  getUserMigrationItemsQueryKey
} from '@/gen/oas/api/@tanstack/vue-query.gen'
const { t, te, d } = useI18n()

const userMigrationItemsOpts = computed(() => getUserMigrationItemsOptions())
const userMigrationItemsQueryKey = computed(() => getUserMigrationItemsQueryKey())
const {
  isPending: userMigrationItemsIsPending,
  isError: userMigrationItemsIsError,
  error: userMigrationItemsError,
  data: userMigrationItems
} = useQuery<GetUserMigrationItemsResponse>({
  ...userMigrationItemsOpts.value,
  queryKey: userMigrationItemsQueryKey,
  retry: false
})

const isPending = computed(() => userMigrationItemsIsPending.value)

const isError = computed(() => userMigrationItemsIsError.value)
const error = computed(() => userMigrationItemsError.value)

// TODO: Type this!
type UserMigrationError = ApiUserMigrationError['description_code'] | 'unknown'

const isUserMigrationError = (error: string): error is UserMigrationError => {
  switch (error) {
    case 'unknown':
    case 'invalid_token':
    case 'same_user_migration':
    case 'different_category_migration':
    case 'role_migration_admin':
    case 'role_migration_user':
    case 'migration_desktop_quota_error':
    case 'migration_template_quota_error':
    case 'migration_media_quota_error':
    case 'migration_deployments_quota_error':
      return true

    default:
      return false
  }
}

const userMigrationError = ref<UserMigrationError | undefined>(
  (() => {
    return error
  })()
)
const userMigrationErrorMsg = computed(() => {
  const baseKey = 'api.user_migration.errors.'
  const key = baseKey + userMigrationError.value

  // Check if the error exists in the base locale
  if (te(key, 'en-US')) {
    return t(key)
  }

  return t(baseKey + 'unknown')
})

/*
 * View logic
 */
import { ref } from 'vue'

const itemsKind = ref([
  {
    title: 'Desktops',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'monitor-02'
  },
  {
    title: 'Templates',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'colors'
  },
  {
    title: 'Media',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'disc-02'
  },
  {
    title: 'Deployments',
    count: 0,
    colorClass: 'text-brand-600',
    icon: 'layout-alt-04'
  }
])

const shownTables = ref([])

const showItemTable = (title: string) => {
  const lowerCaseTitle = title.toLowerCase()
  shownTables.value = shownTables.value.includes(lowerCaseTitle)
    ? shownTables.value.filter((item) => item !== lowerCaseTitle)
    : [...shownTables.value, lowerCaseTitle]
}

/*
 * Actions
 */
const confirmMigration = async () => {
  const { error, response } = await postUserMigrationAuto()

  if (error !== undefined) {
    if (error.error) {
      userMigrationError.value = error.error
      return
    }

    userMigrationError.value = 'unknown'
    return
  }

  return response
}
</script>

<template>
  <MigrationLayout>
    <template #main>
      <Skeleton v-if="isPending" class="h-6" />
      <CardBox v-else-if="isError" icon="alert-circle">
        <p class="text-lg font-semibold text-gray-900">The user can't be migrated:</p>
        {{ error }}
        <ul>
          <li
            v-for="err in error"
            :key="err.description_code"
            class="text-md font-normal text-gray-600"
          >
            {{ err.description }}
            {{ err }}
          </li>
        </ul>
      </CardBox>
      <div v-else class="flex items-center justify-center space-x-8 space-y-8">
        <MigrationNotification />
        <div v-for="item in itemsKind" :key="item.title">
          <MigrationItemBox
            :loading="isPending"
            :title="item.title"
            :count="userMigrationItems[item.title.toLowerCase()].length"
            :color-class="item.colorClass"
            :icon="item.icon"
            class="transition-transform duration-300 ease-in-out transform hover:scale-105 cursor-pointer"
            @click="showItemTable(item.title)"
          >
            <Tooltip title="Click me!"> </Tooltip>
          </MigrationItemBox>
          <MigrationItemTable
            :v-if="shownTables.includes(item.title.toLowerCase())"
            :loading="isPending"
            :title="item.title"
            :items="userMigrationItems[item.title.toLowerCase()]"
          />
        </div>
        <!-- Button to confirm the migration -->
        <div class="flex justify-center mt-8">
          <Button hierarchy="primary" size="lg" :disabled="isPending" @click="confirmMigration">
            Confirm migration
          </Button>
        </div>
        <Alert v-if="userMigrationError" variant="destructive">
          <AlertDescription>{{ userMigrationErrorMsg }}</AlertDescription>
        </Alert>
        <Alert v-if="response" variant="success">
          <AlertDescription>The migration was successful!</AlertDescription>
        </Alert>
      </div>
    </template>
  </MigrationLayout>
</template>
