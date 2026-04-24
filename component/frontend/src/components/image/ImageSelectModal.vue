<script setup lang="ts">
import { ref, watch, defineEmits, defineProps } from 'vue'
import Modal from '@/components/modal/Modal.vue'
import Button from '@/components/ui/button/Button.vue'
import Icon from '@/components/icon/Icon.vue'
// import InputFile from '@/components/ui/input/InputFile.vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  open: Boolean,
  modelValue: Boolean,
  initialSelected: String,
  maxWidth: {
    type: String,
    default: '192'
  }
})
const emit = defineEmits(['update:open', 'select'])
const { t } = useI18n()

const show = ref(props.open || props.modelValue)
const selectedImage = ref<string | null>(props.initialSelected || null)

watch(
  () => props.open,
  (v) => (show.value = v)
)
watch(
  () => props.modelValue,
  (v) => (show.value = v)
)
watch(show, (v) => emit('update:open', v))
watch(
  () => props.initialSelected,
  (v) => (selectedImage.value = v)
)

const stockImages = Array.from({ length: 48 }, (_, i) => `/assets/img/desktops/stock/${i + 1}.jpg`)

const selectStockImage = (imgUrl: string) => {
  selectedImage.value = imgUrl
}

const applySelectedImage = () => {
  if (selectedImage.value) {
    emit('select', selectedImage.value)
    show.value = false
  }
}
</script>

<template>
  <Modal
    :open="show"
    :title="t('components.card.preview.select-image')"
    :description="t('components.card.preview.select-image-description')"
    :max-width="maxWidth"
    @close="show = false"
  >
    <template #default>
      <div class="gap-4 flex-col flex max-h-40 sm:max-h-60 md:max-h-80 lg:max-h-96 xl:max-h-120">
        <!-- TODO: File select input component to select image -->

        <!-- <InputFile accept="image/*"/> -->
        <div class="grid grid-cols-4 pt-1 gap-6 overflow-y-auto">
          <div
            v-for="img in stockImages"
            :key="img"
            class="relative cursor-pointer"
            @click="selectStockImage(img)"
          >
            <img
              :src="img"
              class="w-full h-24 object-cover rounded-md border transition-all"
              :class="
                selectedImage === img
                  ? 'border-4 border-success-600'
                  : 'border hover:ring-success-300 hover:ring-2'
              "
              :alt="'Stock image ' + img"
            />
            <div
              v-if="selectedImage === img"
              class="absolute top-0 right-0 w-5 h-5 bg-success-600 rounded-full m-3 flex items-center justify-center"
            >
              <Icon name="check" size="xs" stroke-color="base-white" />
            </div>
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-center gap-3">
        <Button hierarchy="link-color" @click="show = false">
          {{ t('modals.cancel') }}
        </Button>
        <Button
          hierarchy="primary"
          class="w-64"
          :disabled="!selectedImage"
          @click="applySelectedImage"
        >
          {{ t('modals.confirm') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
