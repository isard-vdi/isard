<script lang="ts" setup>
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { useI18n } from 'vue-i18n'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()
console.log(t('views.migration.notification.description.user'))
</script>

<template>
  <Alert variant="destructive" class="flex flex-col items-center justify-center h-full">
    <Icon
      name="alert-circle"
      class="rounded-[1px] outline outline-1 outline-offset-[10px] outline-gray-warm-300"
    />
    <AlertTitle>Important information when performing a migration:</AlertTitle>
    <AlertDescription class="whitespace-pre-line">
      {{ t('views.migration.notification.description.user') }}
    </AlertDescription>
  </Alert>
</template>
