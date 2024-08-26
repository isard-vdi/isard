<template>
  <div>
    <b-row class="mt-2">
      <h4
        class="p-2 mt-2 cursor-pointer"
        @click="collapseVisible = !collapseVisible"
      >
        <strong>{{ $t('forms.domain.image.title') }}</strong>
        <b-icon
          class="ml-2"
          :icon="collapseVisible ? 'chevron-up' : 'chevron-down'"
        />
      </h4>
    </b-row>
    <b-collapse
      id="collapse-advanced"
      v-model="collapseVisible"
      class="mt-2"
    >
      <b-row v-if="editDomainId">
        <b-col
          cols="12"
          xl="4"
        >
          <b-form-file
            v-model="imageFile"
            :browse-text="$t('components.statusbar.select')"
            placeholder=""
            size="sm"
          />
        </b-col>
        <b-col
          cols="12"
          xl="4"
        >
          <b-button
            :disabled="imageFile === null"
            :pill="true"
            variant="outline-primary"
            size="sm"
            @click="onClickUploadImageFile()"
          >
            {{ `${$t("components.statusbar.upload-file")}` }}
          </b-button>
        </b-col>
      </b-row>
      <b-row align-h="center">
        <b-col
          v-for="image in items"
          :key="image.id"
          cols="auto"
          class="m-2 p-2"
        >
          <IsardImage
            :image-url="image.url"
            :image-id="image.id"
            :image-class="image.id === domain.image.id ? 'selected-image' : 'desktop-image'"
            @imageClicked="onClickChangeDesktopImage(image.id, image.type)"
          />
        </b-col>
      </b-row>
      <b-collapse />
    </b-collapse>
  </div>
</template>

<script>
import { computed, ref } from '@vue/composition-api'
import IsardImage from '@/components/images/IsardImage.vue'

export default {
  components: { IsardImage },
  setup (_, context) {
    const $store = context.root.$store
    const collapseVisible = ref(false)
    const imageFile = ref(null)
    const editDomainId = computed(() => $store.getters.getEditDomainId)
    const domain = computed(() => $store.getters.getDomain)

    const items = computed(() => $store.getters.getImages)
    const onClickChangeDesktopImage = (imageId, imageType) => {
      $store.dispatch('changeImage', { id: imageId, type: imageType })
    }

    const onClickUploadImageFile = () => {
      if (imageFile.value !== null) {
        $store.dispatch('uploadImageFile', { file: imageFile.value, filename: imageFile.value.name })
      }
    }

    return {
      items,
      editDomainId,
      domain,
      imageFile,
      onClickChangeDesktopImage,
      onClickUploadImageFile,
      collapseVisible
    }
  }
}
</script>
