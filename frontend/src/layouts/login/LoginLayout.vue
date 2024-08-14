<script setup lang="ts">
import { computed } from 'vue'
import logoUrl from '@/assets/logo.svg'

interface Props {
  version?: string
}

const props = defineProps<Props>()
const isardVdiUrl = 'https://isardvdi.com'
const versionUrl = computed(() =>
  props.version ? `https://gitlab.com/isard/isardvdi/-/releases/${props.version}` : ''
)
</script>

<template>
  <div class="columns-2 gap-0 h-screen">
    <!-- Left panel (cover image) -->
    <div class="h-full bg-black"></div>

    <!-- Right panel (login form) -->
    <div class="h-full p-[32px] flex flex-col justify-between">
      <!-- Language selector -->
      <div class="self-end">
        <p>IDIOMA</p>
      </div>

      <!-- Login form -->
      <div class="self-center flex flex-col w-[360px]">
        <img class="self-start" :src="logoUrl" alt="IsardVDI logo" />
        <h1 class="mt-[46px] mb-[32px] text-display-sm font-semibold text-gray-warm-900">
          Iniciar sesión
        </h1>
        <div>
          <slot />
        </div>
      </div>

      <!-- Extra info -->
      <div class="flex justify-between">
        <div>
          <p>Funciona amb <a class="font-bold hover:underline" :href="isardVdiUrl">IsardVDI</a></p>
        </div>

        <div>
          <a v-if="props.version" class="hover:underline" :href="versionUrl">{{ props.version }}</a>
        </div>
      </div>
    </div>
  </div>
</template>
