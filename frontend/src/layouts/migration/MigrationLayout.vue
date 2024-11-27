<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="flex h-full min-h-screen overflow-y-auto">
    <div class="w-full md:w-full h-full min-h-screen p-[32px] flex flex-col justify-between">
      <div class="self-center flex flex-col w-full">
        <h1
          class="mt-[46px] mb-[32px] text-center text-display-sm font-semibold text-gray-warm-900"
        >
          {{ t('layouts.migration.title') }}
        </h1>
        <div>
          <slot name="main" />
        </div>
      </div>
    </div>
  </div>
</template>
