<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TooltipProvider from '@/components/ui/tooltip/TooltipProvider.vue'
import { appTitle } from './lib/constants'
import { isString } from './lib/utils'
import { useI18n } from 'vue-i18n'
import { i18n } from './lib/i18n'
import { desktopTimeout } from '@/lib/desktop-timeout'
import NotificationModal from '@/components/modal/NotificationModal.vue'
import { Toaster } from '@/components/ui/toast'

const route = useRoute()
const { t, n } = useI18n()

const updateTitle = () => {
  const base =
    route.meta.title && isString(route.meta.title)
      ? `${appTitle} - ${t(route.meta.title)}`
      : appTitle

  const title = desktopTimeout.value
    ? t('router.notification-title-template', {
        n: n(1),
        title: base
      })
    : base

  document.title = title
}

watch([() => route.meta.title, i18n.global.locale, desktopTimeout], updateTitle)
</script>

<template>
  <TooltipProvider>
    <RouterView />
    <Toaster position="top-right" />
    <NotificationModal />
  </TooltipProvider>
</template>
