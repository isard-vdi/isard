<script setup lang="ts">
import { ref } from 'vue'
import CardTag from './CardTab.vue'
import CardHeader from './CardHeader.vue'
import CardContent from './CardContent.vue'
import CardFooter from './CardFooter.vue'
import { InputField } from '@/components/input-field'
import { useI18n } from 'vue-i18n'
import Button from '@/components/ui/button/Button.vue'
import mountains from '@/assets/img/mountains.svg'
import { computed } from 'vue'

const { t } = useI18n()

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  description: {
    type: String,
    default: ''
  },

  customImage: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:title', 'update:description', 'update:customImage'])

const title = computed({
  get: () => props.title,
  set: (value) => emit('update:title', value)
})

const description = computed({
  get: () => props.description,
  set: (value) => emit('update:description', value)
})

const backgroundImage = computed({
  get: () => props.customImage || mountains,
  set: (value) => emit('update:customImage', value)
})

const fileInputRef = ref<HTMLInputElement | null>(null)
const showImageModal = ref(false)

const handleImageClick = () => {
  showImageModal.value = true
}

const handleImageSelected = (img: string) => {
  backgroundImage.value = img
}
</script>

<template>
  <div class="card rounded-lg overflow-hidden shadow-md relative">
    <CardTag kind="lab" class="absolute top-0 left-0 z-0" />
    <CardHeader
      :background-image="backgroundImage"
      :title="title"
      :description="description"
      :desktops-count="0"
      :card-menus="['image']"
      @image-click="handleImageClick"
    >
      <CardContent class="w-full">
        <div class="flex flex-col gap-3 mt-2">
          <InputField
            v-model="title"
            type="text"
            class="w-full"
            :placeholder="t('components.card.preview.placeholder.title') + '*'"
          />
          <InputField
            v-model="description"
            type="text"
            :placeholder="t('components.card.preview.placeholder.description')"
          />
        </div>
      </CardContent>
    </CardHeader>

    <CardFooter>
      <Button
        hierarchy="primary"
        icon="log-in-04"
        icon-stroke-color="var(--base-white)"
        class="flex items-center gap-2 h-10 px-4 text-base font-semibold rounded-xl border transition"
        :disabled="true"
      >
        {{ t('components.card.button.access') }}
      </Button>
    </CardFooter>
  </div>
</template>

<style scoped>
.card {
  background-color: white;
  width: 426px;
  height: 310px;
  display: flex;
  flex-direction: column;
}
</style>
