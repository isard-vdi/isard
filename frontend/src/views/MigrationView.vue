<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { MigrationLayout } from '@/layouts/migration'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { MigrationItemBox, MigrationItemTable, MigrationResultItem } from '@/components/migration'
import { Skeleton } from '@/components/ui/skeleton'
import {
  postUserMigrationAuto,
  type PostUserMigrationAutoResponse,
  type GetUserMigrationItemsError,
  type GetUserMigrationItemsResponse
} from '@/gen/oas/api'

import { useQuery } from '@tanstack/vue-query'

import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { AutoForm } from '@/components/ui/auto-form'
import { Button } from '@/components/ui/button'

import {
  getUserOptions,
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
} = useQuery<GetUserMigrationItemsResponse, Error>({
  queryKey: userMigrationItemsQueryKey.value,
  ...userMigrationItemsOpts.value,
  retry: false
})

// TODO: provider data should be unified in the authentication OAS definition
const {
  isPending: getUserIsPending,
  isError: getUserIsError,
  error: getUserError, // TODO: handle this error
  data: getUser
} = useQuery(getUserOptions())

const isPending = computed(() => userMigrationItemsIsPending.value || getUserIsPending.value)
const isError = computed(() => userMigrationItemsIsError.value || getUserIsError.value)
const error = computed(() => userMigrationItemsError.value)

// TODO: Type this!
type UserMigrationItemsError =
  | GetUserMigrationItemsError['errors'][number]['description_code']
  | 'unknown'

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

const userMigrationItemsErrorMsgs = computed(() => {
  if (!isError.value || !userMigrationItemsError.value) {
    return undefined
  }

  // TODO: This is horrible
  const aaa = JSON.parse(userMigrationItemsError.value.message) as GetUserMigrationItemsError

  const errorMsgs: Array<string> = []
  const baseKey = 'api.user_migration.errors.'

  if (!aaa.errors) {
    errorMsgs.push(t(baseKey + 'unknown'))
    return errorMsgs
  }

  for (const err of aaa.errors) {
    const key = baseKey + err.description_code

    // Check if the error exists in the base locale
    if (te(key, 'en-US')) {
      errorMsgs.push(t(key))
      continue
    }

    errorMsgs.push(t(baseKey + 'unknown'))
  }

  return errorMsgs
})

/*
 * View logic
 */
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

const shownTables = ref(Array<string>())

const showItemTable = (title: string) => {
  const lowerCaseTitle = title.toLowerCase()
  shownTables.value = shownTables.value.includes(lowerCaseTitle)
    ? shownTables.value.filter((item) => item !== lowerCaseTitle)
    : [...shownTables.value, lowerCaseTitle]
}

/*
 * Actions
 */
const schema = z.object({
  accept: z.boolean().refine((value) => value, {
    message: 'You must accept that .',
    path: ['accept']
  })
})

const fieldConfig = computed(() => {
  return {
    accept: {
      label: t('views.migration.form.accept'),
      inputProps: {
        required: true
      }
    }
  }
})

const form = useForm({
  validationSchema: toTypedSchema(schema)
})

const migrationSuccess = ref(false)
const migrationResponse = ref({} as PostUserMigrationAutoResponse)
const onSubmit = form.handleSubmit(async (values) => {
  console.log('suibmit')
  console.log('values', values)
  const { data, error } = await postUserMigrationAuto()

  if (error !== undefined) {
    console.log('error', error)
    if (error.errors) {
      userMigrationError.value = error.errors
      return
    }

    userMigrationError.value = ['unknown']
    return
  }

  migrationResponse.value = data
  migrationSuccess.value = true
})

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
  <MigrationLayout :go-back="true">
    <template #title>
      <h1 class="mt-[46px] text-center text-display-md font-bold text-gray-warm-800">
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
        class="flex items-center justify-center"
      >
        <Alert variant="destructive" class="w-2/3">
          <AlertTitle>{{ t('views.migration.error.title') }}</AlertTitle>
          <AlertDescription>
            <ul>
              <li v-for="msg in userMigrationItemsErrorMsgs" :key="msg">
                {{ msg }}
              </li>
            </ul>
          </AlertDescription>
        </Alert>
      </div>

      <div v-else-if="migrationSuccess" class="flex items-center justify-center">
        <Alert variant="default" class="w-2/3">
          <AlertTitle class="flex items-center justify-center text-xl text-gray-warm-800">{{
            t('views.migration.success.title')
          }}</AlertTitle>
          <AlertDescription class="p-4 flex flex-col gap-4">
            <!-- Migration result list -->
            <div class="flex flex-col gap-4 p-4">
              <MigrationResultItem
                v-if="migrationResponse?.migrated_desktops !== undefined"
                :title="
                  migrationResponse?.migrated_desktops
                    ? t('views.migration.success.progress.desktops-ok')
                    : t('views.migration.success.progress.desktops-error')
                "
                :success="migrationResponse?.migrated_desktops"
                :description="
                  migrationResponse?.desktops_error
                    ? t('views.migration.success.errors.generic', {
                        type: t('domains.desktops', 2)
                      })
                    : undefined
                "
              />
              <MigrationResultItem
                v-if="migrationResponse?.migrated_templates !== undefined"
                :title="
                  migrationResponse?.migrated_templates
                    ? t('views.migration.success.progress.templates-ok')
                    : t('views.migration.success.progress.templates-error')
                "
                :success="migrationResponse?.migrated_templates"
                :description="
                  migrationResponse?.templates_error
                    ? t('views.migration.success.errors.generic', {
                        type: t('domains.templates', 2)
                      })
                    : undefined
                "
              />
              <MigrationResultItem
                v-if="migrationResponse?.migrated_media !== undefined"
                :title="
                  migrationResponse?.migrated_media
                    ? t('views.migration.success.progress.media-ok')
                    : t('views.migration.success.progress.media-error')
                "
                :success="migrationResponse?.migrated_media"
                :description="
                  migrationResponse?.media_error
                    ? t('views.migration.success.errors.generic', {
                        type: t('domains.media', 2)
                      })
                    : undefined
                "
              />
              <MigrationResultItem
                v-if="migrationResponse?.migrated_deployments !== undefined"
                :title="
                  migrationResponse?.migrated_deployments
                    ? t('views.migration.success.progress.deployments-ok')
                    : t('views.migration.success.progress.deployments-error')
                "
                :success="migrationResponse?.migrated_deployments"
                :description="
                  migrationResponse?.deployments_error
                    ? t('views.migration.success.errors.generic', {
                        type: t('domains.deployments', 2)
                      })
                    : undefined
                "
              />
              <MigrationResultItem
                v-if="migrationResponse?.rb_deleted !== undefined"
                :title="t('views.migration.success.progress.recycle-bin-ok')"
                :success="migrationResponse?.rb_deleted"
              />
            </div>

            <p class="px-8">
              {{
                migrationResponse?.migrated_desktops === false ||
                migrationResponse?.migrated_templates === false ||
                migrationResponse?.migrated_media === false ||
                migrationResponse?.migrated_deployments === false
                  ? t('views.migration.success.description.error')
                  : t('views.migration.success.description.ok')
              }}
            </p>

            <div class="flex flex-row items-center justify-end">
              <Button class="px-8" @click="goToDesktops">{{
                t('views.migration.success.buttons.ok')
              }}</Button>
            </div>
          </AlertDescription>
        </Alert>
      </div>

      <div v-else class="flex flex-col items-center justify-center gap-8 mb-[32px]">
        <div class="w-full flex flex-row flex-wrap gap-8 items-start justify-center">
          <template v-for="item in itemsKind" :key="item.title">
            <div
              v-if="userMigrationItems[item.title.toLowerCase()].length > 0"
              class="w-64 flex flex-col gap-4"
            >
              <MigrationItemBox
                :loading="isPending"
                :title="t(`domains.capitalized.${item.title.toLowerCase()}`, 2)"
                :count="userMigrationItems[item.title.toLowerCase()].length"
                :color-class="item.colorClass"
                :warning="itemQuotaExceeded(item.title.toLowerCase())"
                :icon="item.icon"
                class="transition-transform duration-300 ease-in-out transform hover:scale-105 cursor-pointer"
                @click="showItemTable(item.title)"
              />
              <MigrationItemTable
                v-if="!shownTables.includes(item.title.toLowerCase())"
                :loading="isPending"
                :title="t(`domains.capitalized.${item.title.toLowerCase()}`, 2)"
                :items="userMigrationItems[item.title.toLowerCase()]"
                class="max-h-[30vh] overflow-y-auto"
              />
            </div>
          </template>
        </div>

        <div class="flex items-center justify-center">
          <Alert variant="destructive" class="w-full max-w-max">
            <Icon
              name="alert-circle"
              class="rounded-[1px] outline outline-1 outline-offset-[10px] outline-gray-warm-300"
            />
            <AlertTitle>
              <h1 class="text-md font-semibold mb-2">
                {{ t('views.migration.notification.title') }}
              </h1>
            </AlertTitle>
            <AlertDescription>
              <p class="font-semibold">
                {{
                  t('views.migration.notification.description.delete_user', {
                    old_user_name: userMigrationItems?.users[0].name,
                    old_user_provider: userMigrationItems?.users[0].provider
                  })
                }}
              </p>
              <p class="whitespace-pre-line">
                {{ t('views.migration.notification.description.description') }}
              </p>

              <p class="font-semibold mt-2">
                {{ t('views.migration.notification.description.footer') }}
              </p>
            </AlertDescription>
          </Alert>
        </div>

        <!-- Button to confirm the migration -->
        <div>
          <AutoForm
            :form="form"
            :schema="schema"
            :field-config="fieldConfig"
            class="flex flex-row justify-center gap-8 items-start"
            @submit="onSubmit"
          >
            <Button type="submit" hierarchy="primary" size="lg" :disabled="isPending">
              {{ t('views.migration.form.submit') }}
            </Button>
          </AutoForm>
        </div>
      </div>
    </template>
  </MigrationLayout>
</template>
