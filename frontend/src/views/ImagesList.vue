<template>
  <b-container
    fluid
    class="main-container px-3 pl-xl-5 pr-xl-5 pt-3"
  >
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
          image-class="desktop-image"
          @imageClicked="onClickChangeDesktopImage(image.id, image.type)"
        />
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import i18n from '@/i18n'
import { computed } from '@vue/composition-api'
import { mapActions, mapGetters } from 'vuex'
import IsardImage from '@/components/images/IsardImage.vue'

export default {
  components: { IsardImage },
  setup (_, context) {
    const $store = context.root.$store

    $store.dispatch('fetchDesktopImages')

    const items = computed(() => $store.getters.getImages)

    return {
      items
    }
  },
  computed: {
    ...mapGetters(['getImagesListItemId'])
  },
  mounted () {
    if (this.getImagesListItemId.length < 1) {
      this.navigate('desktops')
    }
  },
  methods: {
    ...mapActions([
      'changeImage',
      'navigate'
    ]),
    onClickChangeDesktopImage (imageId, imageType) {
      this.$snotify.clear()

      const yesAction = () => {
        this.$snotify.clear()
        this.changeImage({ id: imageId, type: imageType })
      }

      const noAction = () => {
        this.$snotify.clear() // default
      }

      this.$snotify.prompt(`${i18n.t('messages.confirmation.change-image', { name: this.getCardTitle })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }
  }
}
</script>
