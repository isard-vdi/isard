<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { getUserNotificationTriggerDisplayOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { NotificationDisplayEnum } from '@/gen/oas/apiv4'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { NotificationList } from '@/components/notification'
import { Icon } from '@/components/icon'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import router from '@/router'

import { useI18n } from 'vue-i18n'

const { t, te } = useI18n()
const route = useRoute()

const {
  isPending: notificationsIsPending,
  isError: notificationsIsError,
  error: notificationsError,
  data: notificationsData
} = useQuery(
  getUserNotificationTriggerDisplayOptions({
    path: {
      trigger: route.params.trigger,
      display: NotificationDisplayEnum.FULLPAGE
    }
  })
)

const isPending = computed(() => notificationsIsPending.value)
const isError = computed(() => notificationsIsError.value)
const errorMessage = computed(() => {
  const err = notificationsError.value
  const code = err && 'description_code' in err ? err.description_code : undefined
  return code && te(code) ? t(code) : t('views.notifications.error.generic')
})
const data = computed(() => notificationsData.value)
</script>
<template>
  <div class="relative">
    <div class="flex justify-end w-full">
      <Button
        icon="arrow-right"
        hierarchy="link-color"
        class="text-lg mr-10"
        @click="router.push({ name: 'desktops' })"
      >
        {{ t('views.notifications.go-to-desktops') }}
      </Button>
    </div>
    <div
      v-if="isPending"
      class="flex items-center justify-center mt-3"
      role="status"
      aria-busy="true"
    >
      <span class="sr-only">{{ t('views.notifications.loading') }}</span>
      <ul class="flex w-full max-w-2xl flex-col gap-3" aria-hidden="true">
        <li v-for="i in 3" :key="i">
          <div class="flex flex-col gap-2 rounded-lg border border-gray-warm-300 p-5 pl-3">
            <div class="flex gap-4 items-center">
              <div class="self-stretch border-r border-brand-200 flex items-center pr-3">
                <Skeleton class="size-8 shrink-0 rounded-full" />
              </div>
              <div class="flex w-full flex-col gap-2">
                <Skeleton class="h-5 w-1/2" />
                <Skeleton class="h-4 w-3/4" />
                <Skeleton class="h-3 w-24 ml-auto" />
              </div>
            </div>
          </div>
        </li>
      </ul>
    </div>
    <Alert
      v-else-if="isError"
      variant="destructive"
      class="w-fit mx-auto p-6 flex flex-col gap-1 text-center"
    >
      <Icon name="alert-circle" stroke-color="error-600" size="lg" aria-hidden="true" />
      <AlertTitle>{{ t('views.notifications.error.title') }}</AlertTitle>
      <AlertDescription>{{ errorMessage }}</AlertDescription>
    </Alert>
    <div v-else class="mt-3 relative w-full">
      <div v-if="!data?.notifications?.length" class="text-center">
        <div
          class="flex gap-3 w-fit mx-auto items-center bg-brand-200 p-3 rounded-xl border border-brand-600/40"
          role="status"
        >
          <Icon name="info-circle" size="md" aria-hidden="true" stroke-color="brand-700" />
          <p class="font-medium text-md text-brand-700">
            {{ t('views.notifications.no-notifications') }}
          </p>
        </div>
      </div>
      <div v-else class="z-10 relative mt-3">
        <NotificationList :notifications="data.notifications" class="mx-auto" />
      </div>
    </div>
    <img
      src="@/assets/img/bg-dots.svg"
      class="-z-10 size-300 absolute opacity-50 -top-70 left-1/2 -translate-x-1/2"
      aria-hidden="true"
    />
  </div>
</template>
