<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/button/Button.vue'
import DataTable from '@/components/data-table/DataTable.vue'
import Input from '@/components/ui/input/Input.vue'
import Icon from '@/components/icon/Icon.vue'
import Badge from '@/components/ui/badge/Badge.vue'

import { getLabUserDesktopsApiV4ItemLabLabIdUserUserIdDesktopsGetQueryKey } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getLabUserDesktopsApiV4ItemLabLabIdUserUserIdDesktopsGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

// Retrieve the id from the route
const route = useRoute()
const { t } = useI18n()
const labId = route.params.id as string
console.log(labId)
// Retrieve the userId from the store claims
const authStore = useAuthStore()
const userId = authStore.user.user_id as string

const labDesktopsOpts = computed(() =>
  getLabUserDesktopsApiV4ItemLabLabIdUserUserIdDesktopsGetOptions({
    path: {
      lab_id: labId,
      user_id: userId
    }
  })
)

const { isPending, isError, error, data } = useQuery({
  ...labDesktopsOpts.value
})

const inputProps = {
  defaultValue: '',
  placeholder: t('views.desktops.search'),
  size: 'sm',
  destructive: false,
  icon: 'search-lg'
}

const headers = [
  { name: t('views.deployments.headers.name'), key: 'name' },
  { name: t('views.deployments.headers.description'), key: 'description' },
  { name: 'Status', key: 'status' },
  { name: '', key: 'action' }
]

async function goToDesktopDirectViewer(desktopId: string) {
  // Fetch (or create) the desktop share link and open the direct viewer URL
  // in a new tab. apiv4 split the v3 PUT /desktop/{id}/jumperurl get-or-create
  // into two separate routes (get-share-link + update-share-link), so the
  // client handles the "create when missing" logic here.
  try {
    const headers = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authStore.token}`
    }
    const getResp = await fetch(`/api/v4/item/desktop/${desktopId}/get-share-link`, {
      method: 'GET',
      headers
    })
    if (!getResp.ok) throw new Error('Failed to fetch share link')
    let data = await getResp.json()
    if (!data || data.jumperurl === false || data.jumperurl == null) {
      const updateResp = await fetch(`/api/v4/item/desktop/${desktopId}/update-share-link`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ enabled: true })
      })
      if (!updateResp.ok) throw new Error('Failed to create share link')
      data = await updateResp.json()
    }
    const directViewerUrl = `${window.location.protocol}//${window.location.host}/vw/${data.jumperurl}`
    window.open(directViewerUrl, '_blank')
  } catch (error) {
    console.error('Error fetching direct viewer URL:', error)
  }
}

const searchTerm = ref('')

const rows = computed(() => {
  if (!data.value || !data.value.desktops) return []

  return data.value.desktops.map((desktop) => ({
    id: desktop.id,
    status: desktop.status,
    name: desktop.name,
    description: desktop.description
    // TODO: handle here the action buttons
  }))
})

const filteredRows = computed(() => {
  return rows.value.filter((row) => {
    return row.name.toLowerCase().includes(searchTerm.value.toLowerCase())
  })
})
</script>
<template>
  <div class="w-full max-w-(--breakpoint-2xl) mx-auto px-4 sm:px-6 lg:px-12">
    <div class="mt-10 w-full">
      <div class="flex justify-between items-center mb-8">
        <Input v-bind="inputProps" v-model="searchTerm" />
      </div>

      <div class="overflow-x-auto bg-white rounded-lg border border-[#D7D3D0] p-6 w-full">
        <div v-if="isPending" class="text-center text-gray-500">
          {{ t('views.deployments.loading') }}
        </div>
        <div v-else-if="isError" class="text-center text-error-500">
          {{ t('views.deployments.error') }}
        </div>
        <DataTable v-else :headers="headers" :rows="filteredRows">
          <template #cell-kind="{ value }">
            <Icon
              :name="value === 'lab' ? 'beaker-02' : 'layout-alt-04'"
              :featured="value"
              size="xxl"
            />
          </template>
          <template #cell-action="{ row }">
            <Button
              title="Go to direct viewer"
              hierarchy="link-gray"
              size="sm"
              icon="tv-03"
              icon-size="md"
              @click.stop="goToDesktopDirectViewer(row.id)"
            />
          </template>
        </DataTable>
      </div>
    </div>
  </div>
</template>
