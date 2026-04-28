<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'

import { getUserConfigOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  EDIT_FORM_ROUTES,
  VUE3_TO_VUE2,
  resolveVue2Path,
  type FrontendMode
} from '@/lib/frontendModeMap'

const route = useRoute()
const { t } = useI18n()

const { data: userConfig } = useQuery({
  ...getUserConfigOptions(),
  staleTime: Infinity
})

const visible = computed(() => {
  const mode = (userConfig.value as { frontend_mode?: FrontendMode } | undefined)?.frontend_mode
  if (mode !== 'all') return false
  const name = route.name as string | undefined
  if (!name) return false
  return !EDIT_FORM_ROUTES.has(name)
})

const target = computed(() => resolveVue2Path(route))
const hasEquivalent = computed(() => {
  const name = route.name as string | undefined
  return name != null && name in VUE3_TO_VUE2
})

function switchFrontend() {
  if (!target.value) return
  window.location.assign(target.value)
}
</script>

<template>
  <button
    v-if="visible"
    type="button"
    class="fixed bottom-4 right-4 z-50 rounded-full bg-brand-700 px-4 py-2 text-sm font-semibold text-base-white shadow-lg hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-gray-warm-300"
    :disabled="!hasEquivalent"
    :title="hasEquivalent ? t('frontend_toggler.to_vue2') : t('frontend_toggler.no_equivalent')"
    @click="switchFrontend"
  >
    {{ hasEquivalent ? t('frontend_toggler.to_vue2') : t('frontend_toggler.no_equivalent') }}
  </button>
</template>
