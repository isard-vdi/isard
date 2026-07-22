<!-- TODO: Must be deployment card -->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import Card from '@/components/card/Card.vue'
import Button from '@/components/ui/button/Button.vue'
import mountains from '@/assets/img/mountains.svg'

const { t } = useI18n()
const router = useRouter()

interface Lab {
  id: string
  name: string
  description: string
  total_desktops: number
  background_image?: string
}

const props = defineProps({
  lab: {
    type: Object as () => Lab,
    required: true
  }
})
</script>
<template>
  <Card
    :key="props.lab.id"
    kind="lab"
    :title="props.lab.name"
    :description="props.lab.description"
    :background-image="props.lab.background_image || mountains"
    :desktops-count="props.lab.total_desktops"
  >
    <template #footer>
      <div class="h-[68px] bg-white rounded-b-lg border-x border-b z-1">
        <Button
          hierarchy="primary"
          icon-stroke-color="base-white"
          icon="arrow-right"
          :disabled="props.lab.total_desktops === 0"
          class="flex items-center gap-2 h-10 px-4 text-base font-semibold rounded-xl border transition"
          @click="router.push({ name: 'lab-desktops', params: { id: props.lab.id } })"
        >
          {{ t('components.card.button.access') }}
        </Button>
      </div>
    </template>
  </Card>
</template>
