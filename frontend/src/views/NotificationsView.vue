<script setup lang="ts">
import { getUserNotifications, type GetUserNotificationsResponse } from '@/gen/oas/api'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { getUserNotificationsOptions } from '@/gen/oas/api/@tanstack/vue-query.gen'
import { Skeleton } from '@/components/ui/skeleton'
import { SinglePageLayout } from '@/layouts/single-page'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'

import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const route = useRoute()

const {
  isPending: notificationsIsPending,
  isError: notificationsIsError,
  error: notificationsError,
  data: notificationsData
} = useQuery(
  getUserNotificationsOptions({
    path: {
      trigger: route.params.trigger,
      display: 'fullpage'
    }
  })
)

const isPending = computed(() => notificationsIsPending.value)
const isError = computed(() => notificationsIsError.value)
const error = computed(() => notificationsError.value)
const data = computed(() => notificationsData.value)
</script>
<template>
  <SinglePageLayout :go-back="true">
    <template #title>
      <h1 class="mt-[46px] text-center text-display-md font-bold text-gray-warm-800">
        {{ t('views.notifications.title') }}
      </h1>
    </template>
    <template #main>
      <div v-if="isPending" class="w-full flex flex-col gap-2 items-center justify-center">
        <Skeleton class="h-4 w-1/3" />
      </div>
      <div v-else-if="isError" class="text-center">
        <Alert variant="destructive" class="w-2/3">
          <AlertTitle>{{ t('views.migration.error.title') }}</AlertTitle>
          <AlertDescription>{{ t(error.description_code) }}</AlertDescription>
        </Alert>
      </div>
      <div v-else class="flex items-center justify-center">
        <div v-if="!data?.notifications" class="text-center">
          <p>{{ t('views.notifications.no-notifications') }}</p>
        </div>
        <div v-else>
          <div v-for="notification in data?.notifications" :key="notification.id">
            <Alert
              v-for="(value, itemType) in notification"
              :key="itemType"
              class="flex flex-col gap-4 m-4"
            >
              <AlertTitle>{{ value.template.title }}</AlertTitle>
              <div v-if="value.notifications && value.action_id != 'custom'">
                <div v-for="(n, index) in value.notifications" :key="index">
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <AlertDescription v-html="n.text"></AlertDescription>
                </div>
              </div>
              <span v-else>
                <!-- eslint-disable-next-line vue/no-v-html -->
                <AlertDescription v-html="value.template.body"></AlertDescription>
              </span>
              <footer class="text-sm text-gray-500">{{ value.template.footer }}</footer>
            </Alert>
          </div>
        </div>
      </div>
    </template>
  </SinglePageLayout>
</template>
