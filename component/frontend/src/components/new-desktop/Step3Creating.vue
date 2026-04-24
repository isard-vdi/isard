<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="flex items-center justify-center min-h-[60vh]">
    <div class="flex flex-col items-center gap-6">
      <Spinner />
      <div class="flex flex-col items-center gap-4">
        <h2 class="text-display-sm font-bold text-gray-warm-800">
          {{ t('views.new-desktop.creating.title') }}
        </h2>
        <p class="text-base text-center text-gray-warm-600 max-w-140">
          {{ t('views.new-desktop.creating.description') }}
        </p>
      </div>
      <Button hierarchy="link-color" @click="router.push({ name: 'desktops' })">
        {{ t('views.new-desktop.success.go-to-desktops') }}
      </Button>
    </div>
  </div>
</template>
