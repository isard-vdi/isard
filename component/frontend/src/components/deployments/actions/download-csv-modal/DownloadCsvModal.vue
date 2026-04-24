<script setup lang="ts">
import { ref } from 'vue'
import { useMutation } from '@tanstack/vue-query'
import { getDeploymentCsvApiV4ItemDeploymentDeploymentIdDownloadCsvGet } from '@/gen/oas/apiv4'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/modal'
import { CheckboxGroup } from '@/components/checkbox-group'
import regenerateUrls from '@/assets/img/modal/regenerate-urls.svg'
import keepUrls from '@/assets/img/modal/keep-urls.svg'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  open?: boolean
  deploymentId: string
  deploymentName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

const { mutate: fetchDownloadCsv, isPending: downloadCsvIsPending } = useMutation({
  mutationFn: async (params: {
    path: { deployment_id: string }
    query: { regenerate: boolean }
  }) => {
    const { data } = await getDeploymentCsvApiV4ItemDeploymentDeploymentIdDownloadCsvGet(params)
    if (!data) throw new Error('No data received')
    return data
  },
  onSuccess: (csvData, variables) => {
    handleClose()
    let csv = csvData
    if (csv.startsWith('"') && csv.endsWith('"')) {
      csv = csv
        .slice(1, -1)
        .replace(/""/g, '"')
        .replace(/\\r\\n|\\n/g, '\n')
    }

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${variables.path.deployment_id}_direct_viewer.csv`
    document.body.appendChild(a)
    a.click()
    setTimeout(() => {
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    }, 100)
  }
})

const handleDownloadCsv = () => {
  fetchDownloadCsv({
    path: { deployment_id: props.deploymentId },
    query: { regenerate: selectedOption.value === 'regenerateUrls' }
  })
}

const selectedOption = ref<'keepUrls' | 'regenerateUrls' | undefined>(undefined)

const handleClose = () => {
  emit('update:open', false)
  emit('close')
  selectedOption.value = undefined
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.deployments.download-csv-modal.title', { name: props.deploymentName })"
    size="3xl"
    class="pt-4"
    @close="handleClose"
  >
    <CheckboxGroup
      v-model="selectedOption"
      kind="card"
      type="single"
      direction="flex-col md:flex-row"
      :items="[
        {
          value: 'keepUrls',
          title: t('components.deployments.download-csv-modal.options.keep-urls.title'),
          description: t('components.deployments.download-csv-modal.options.keep-urls.description'),
          icon: 'equal',
          image: keepUrls,
          class: 'flex-1 mb-1.5'
        },
        {
          value: 'regenerateUrls',
          title: t('components.deployments.download-csv-modal.options.regenerate-urls.title'),
          description: t(
            'components.deployments.download-csv-modal.options.regenerate-urls.description'
          ),
          icon: 'link-broken-01',
          image: regenerateUrls,
          class: 'flex-1 mb-1.5'
        }
      ]"
    />
    <template #footer>
      <Button hierarchy="link-gray" @click="handleClose">
        {{ t('components.deployments.download-csv-modal.cancel') }}
      </Button>
      <Button
        hierarchy="primary"
        :disabled="!selectedOption || downloadCsvIsPending"
        @click="handleDownloadCsv"
      >
        {{ t('components.deployments.download-csv-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
