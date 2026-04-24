<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { MaintenanceLayout } from '@/layouts/maintenance'
import { Locale, setLocale } from '@/lib/i18n'
import { getToken as getAuthToken, useCookies as useAuthCookies, getBearer } from '@/lib/auth'
import {
  apiV4LoginConfigApiV4ItemLoginConfigGetOptions,
  getMaintenanceApiV4MaintenanceGetOptions,
  getMaintenanceApiV4MaintenanceGetQueryKey,
  maintenanceStatusApiV4MaintenanceStatusGetOptions,
  maintenanceStatusApiV4MaintenanceStatusGetQueryKey,
  getMaintenanceTextFrontendApiV4MaintenanceTextFrontendGetOptions,
  getMaintenanceTextFrontendApiV4MaintenanceTextFrontendGetQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const cookies = useAuthCookies()

const maintenanceTextOpts = computed(() =>
  getMaintenanceTextFrontendApiV4MaintenanceTextFrontendGetOptions()
)
const maintenanceTextQueryKey = computed(() =>
  getMaintenanceTextFrontendApiV4MaintenanceTextFrontendGetQueryKey()
)

const {
  isPending: maintenanceTextIsPending,
  isError: maintenanceTextIsError,
  error: maintenanceTextError,
  data: maintenanceText
} = useQuery({
  ...maintenanceTextOpts.value,
  queryKey: maintenanceTextQueryKey,
  refetchOnWindowFocus: true
})

const maintenanceStatusOpts = computed(() => maintenanceStatusApiV4MaintenanceStatusGetOptions())
const maintenanceStatusQueryKey = computed(() =>
  maintenanceStatusApiV4MaintenanceStatusGetQueryKey()
)

const {
  isPending: maintenanceStatusIsPending,
  isError: maintenanceStatusIsError,
  error: maintenanceStatusError,
  data: maintenanceStatus
} = useQuery({
  ...maintenanceStatusOpts.value,
  queryKey: maintenanceStatusQueryKey,
  enabled: computed(() => !getAuthToken(cookies)),
  refetchOnWindowFocus: true,
  retry: false // Don't retry if there's an error, as it probably is a 503
})

const maintenanceOpts = computed(() => getMaintenanceApiV4MaintenanceGetOptions())
const maintenanceQueryKey = computed(() =>
  getMaintenanceApiV4MaintenanceGetQueryKey({
    headers: {
      Authorization: `Bearer ${getBearer(cookies)}`
    }
  })
)

const {
  isPending: maintenanceIsPending,
  isError: maintenanceIsError,
  error: maintenanceError,
  data: maintenance
} = useQuery({
  ...maintenanceOpts.value,
  queryKey: maintenanceQueryKey,
  enabled: computed(() => !!getAuthToken(cookies)),
  refetchOnWindowFocus: true,
  retry: false // Don't retry if there's an error, as it probably is a 503
})

const {
  isPending: configIsPending,
  isError: configIsError,
  error: configError,
  data: config
} = useQuery(apiV4LoginConfigApiV4ItemLoginConfigGetOptions())

const isPending = computed(
  () =>
    (maintenanceIsPending.value && maintenanceStatusIsPending.value) ||
    maintenanceTextIsPending.value ||
    configIsPending.value
)

const isError = computed(
  () =>
    maintenanceIsError.value ||
    maintenanceStatusIsError.value ||
    maintenanceTextIsError.value ||
    configIsError.value
)
const error = computed(
  () =>
    (maintenanceError.value && maintenanceStatusError.value) ||
    maintenanceTextError.value ||
    configError.value
)

// Set the locale if there's a configuration set
watch(config, (newCfg) => {
  if (newCfg?.locale?.default) {
    setLocale(newCfg.locale.default as Locale)
    localStorage.language = newCfg.locale.default
  }
})

const isMaintenance = computed(() => {
  if (isPending.value) {
    return true
  }
  return maintenanceStatus.value?.enabled === true || maintenance.value?.enabled === true
})

// redirect to / if there's no maintenance
if (isMaintenance.value === false) {
  window.location.pathname = '/'
}
watch(isMaintenance, (isMaintenance) => {
  if (isMaintenance === false) {
    window.location.pathname = '/'
  }
})
</script>

<template>
  <MaintenanceLayout
    :loading="isPending"
    :hide-locale-switch="config?.locale?.hide"
    :hide-logo="config?.logo?.hide"
    :title="maintenanceText?.enabled !== false ? maintenanceText?.title || undefined : undefined"
    :description="
      maintenanceText?.enabled !== false ? maintenanceText?.body || undefined : undefined
    "
  ></MaintenanceLayout>
</template>
