<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LocaleSwitch } from '@/components/locale-switch'

const { t } = useI18n()

const isardVdiUrl = 'https://isardvdi.com'

interface Props {
  loading?: boolean
  hideLocaleSwitch?: boolean
  hideLogo?: boolean
  title?: string
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  hideLocaleSwitch: false,
  hideLogo: false,
  title: undefined,
  description: undefined
})
</script>

<template>
  <div class="flex h-screen overflow-y-auto">
    <!-- Left panel (cover image) -->
    <div
      class="hidden md:block w-1/2 h-full bg-cover bg-center bg-cover-img flex px-20 content-center"
    >
      <slot name="cover" />
    </div>

    <!-- Right panel (login form) -->
    <div class="w-full md:w-1/2 h-full p-[32px] flex flex-col justify-between">
      <!-- Language selector -->
      <div class="self-end">
        <LocaleSwitch v-if="!loading && !props.hideLocaleSwitch" />
      </div>

      <!-- Login form -->
      <div class="self-center flex flex-col w-[360px]">
        <img
          v-if="!loading && !props.hideLogo"
          class="self-center"
          :src="'/custom/logo.svg'"
          alt="IsardVDI logo"
        />
        <h1
          v-if="!loading"
          class="mt-[46px] mb-[32px] text-center text-display-sm font-semibold text-gray-warm-900"
        >
          {{ props.title || t('layouts.login.title') }}
        </h1>

        <h2
        v-if="!loading && props.description"
        class="text-center text-md font-semibold mb-[32px]">
          {{ props.description }}
        </h2>
        <div>
          <slot />
        </div>
      </div>

      <!-- Extra info -->
      <div class="self-center flex">
        <div>
          <p>
            {{ t('layouts.login.works-with') }}
            <a class="font-bold hover:underline" :href="isardVdiUrl">IsardVDI</a>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
