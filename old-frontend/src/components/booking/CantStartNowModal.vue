<template>
  <b-modal
    id="cantStartModal"
    v-model="modal.show"
    size="lg"
    :title="modalTitle"
    centered
    hide-footer
    header-class="bg-orange text-white"
    @hidden="closeModal"
  >
    <b-row
      v-if="modal.showChangeProfileAndStartOption"
      class="ml-2 mr-2"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`components.cant-start-now-modal.change-desktop-gpu.text`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="mt-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-primary"
          size="sm"
          @click="changeDesktopGpu"
        >
          {{ $t(`components.cant-start-now-modal.change-desktop-gpu.button`) }}
        </b-button>
      </b-col>
    </b-row>
    <hr v-if="modal.showChangeProfileAndStartOption && !isNewDesktop">
    <b-row
      v-if="!isNewDesktop"
      class="ml-2 mr-2"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`components.cant-start-now-modal.go-to-bookings.text`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="mt-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-primary"
          size="sm"
          @click="onClickBookingDesktop"
        >
          {{ $t(`components.cant-start-now-modal.go-to-bookings.button`) }}
        </b-button>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'

export default {
  setup (_, context) {
    const $store = context.root.$store

    // const item = computed(() => $store.getters.getBookingItem)

    const modal = computed(() => $store.getters.getCantStartNowModal)

    const isNewDesktop = computed(() => !!modal.value.item.newDesktopTemplateId)

    const modalTitle = computed(() => {
      if (!modal.value.showChangeProfileAndStartOption) {
        return i18n.t('components.cant-start-now-modal.title.no-available-profile')
      }
      return isNewDesktop.value
        ? i18n.t('components.cant-start-now-modal.title.template-available-profile')
        : i18n.t('components.cant-start-now-modal.title.available-profile')
    })

    const changeDesktopGpu = () => {
      $store.dispatch('fetchReservablesAvailable', { action: modal.value.item.action })
    }

    const onClickBookingDesktop = () => {
      context.root.$router.push({ name: 'booking', params: { id: modal.value.item.id, type: modal.value.item.type } })
      closeModal()
    }

    const closeModal = () => {
      $store.dispatch('resetCantStartNowModal')
    }

    return {
      closeModal,
      onClickBookingDesktop,
      changeDesktopGpu,
      modal,
      modalTitle,
      isNewDesktop
    }
  }
}
</script>
