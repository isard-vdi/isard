<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TooltipProvider from '@/components/ui/tooltip/TooltipProvider.vue'
import { appTitle } from './lib/constants'
import { isString } from './lib/utils'
import { useI18n } from 'vue-i18n'
import { i18n } from './lib/i18n'

const route = useRoute()
const { t } = useI18n()

const updateTitle = () => {
  if (route.meta.title && isString(route.meta.title)) {
    document.title = `${appTitle} - ${t(route.meta.title)}`
  } else {
    document.title = appTitle
  }
}

watch(
  () => route.meta.title,
  () => {
    updateTitle()
  }
)

watch(i18n.global.locale, () => {
  updateTitle()
})
</script>

<template>
  <TooltipProvider>
    <RouterView />
  </TooltipProvider>
</template>
