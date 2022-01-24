<template>
  <b-modal
    id="eventModal"
    size="lg"
    :title="$t(`components.bookings.item.modal.${modal.type}.modal-title`)"
    v-model="modalShow"
    @hidden="closeModal"
    centered
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <label for="title">{{ $t(`components.bookings.item.modal.title`) }}</label>
        <b-form-input id="title" v-model="modal.title" placeholder="Enter a title"></b-form-input>
      </b-col>
      <b-col cols="6" class="mt-2">
        <label for="eventStartDate">{{ $t(`components.bookings.item.modal.start-date`) }}*</label>
        <b-form-datepicker
          :disabled="modal.type == 'view'"
          id="eventStartDate"
          type="date"
          v-model="modal.startDate"
          :locale="this.$i18n.locale"
        ></b-form-datepicker>
      </b-col>
      <b-col cols="6" class="mt-2">
        <label for="eventStartTime">{{ $t(`components.bookings.item.modal.start-time`) }}*</label>
        <b-form-input
          :disabled="modal.type == 'view'"
          id="eventStartTime"
          type="time"
          v-model="modal.startTime"
        ></b-form-input>
      </b-col>
      <b-col cols="6" class="mt-2">
      <label for="eventEndDate">{{ $t(`components.bookings.item.modal.end-date`) }}*</label>
        <b-form-datepicker
          :disabled="modal.type == 'view'"
          id="eventEndDate"
          type="date"
          v-model="modal.endDate"
          :locale="this.$i18n.locale"
        ></b-form-datepicker>
      </b-col>
      <b-col cols="6" class="mt-2">
        <label for="eventEndTime">{{ $t(`components.bookings.item.modal.end-time`) }}*</label>
        <b-form-input :disabled="modal.type == 'view'" id="eventEndTime" type="time" v-model="modal.endTime"></b-form-input>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          class="float-left"
          variant="outline-danger"
          v-if="modal.type === 'edit'"
          @click="deleteEvent"
        >
          {{ $t(`components.bookings.item.modal.delete.button`) }}
        </b-button>
        <b-button
          squared
          v-if="modal.type === 'create'"
          variant="primary"
          class="float-right"
          @click="createEvent"
        >
          {{ $t(`components.bookings.item.modal.${modal.type}.button`) }}
        </b-button>
        <!-- <b-button
          v-if="modal.type === 'edit'"
          squared
          variant="primary"
          class="float-right"
          @click="editEvent"
        >
          {{ $t(`components.bookings.item.modal.${modal.type}.button`) }}
        </b-button> -->
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import i18n from '@/i18n'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const item = computed(() => $store.getters.getBookingItem)
    const view = computed(() => $store.getters.getBookingView)

    const modalShow = computed({
      get: () => $store.getters.getBookingModalShow,
      set: (value) => $store.commit('setBookingModalShow', value)
    })

    const modal = computed({
      get: () => $store.getters.getBookingEventModal,
      set: (value) => $store.commit('setBookingEventModal', {
        title: value.title,
        type: value.type,
        startDate: value.startDate,
        startTime: value.startTime,
        endDate: value.endDate,
        endTime: value.endTime
      })
    })

    const createEvent = () => {
      $store.dispatch('createEvent', {
        elementId: item.value.id,
        elementType: view.value.itemType,
        title: modal.value.title,
        date: `${modal.value.startDate} ${modal.value.startTime}`,
        end: `${modal.value.endDate} ${modal.value.endTime}`
      }).then(() => {
        DateUtils.sleep(100)
        const eventsData = {
          itemId: item.value.id,
          itemType: view.value.itemType,
          startDate: view.value.start,
          endDate: view.value.end,
          returnType: 'all'
        }
        $store.dispatch('fetchEvents', eventsData)
      })
    }

    const closeModal = () => {
      $store.dispatch('resetModalData')
      $store.dispatch('showBookingModal', false)
    }

    const deleteEvent = (toast) => {
      context.root.$snotify.clear()

      const yesAction = () => {
        toast.valid = true // default value
        $store.dispatch('deleteEvent', {
          id: modal.value.id
        }).then(() => {
          DateUtils.sleep(100)
          const eventsData = {
            itemId: item.value.id,
            itemType: view.value.itemType,
            startDate: view.value.start,
            endDate: view.value.end,
            returnType: 'all'
          }
          $store.dispatch('fetchEvents', eventsData)
        })
        context.root.$snotify.remove(toast.id)
      }

      const noAction = (toast) => {
        context.root.$snotify.remove(toast.id) // default
      }

      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.delete-event', { name: modal.value.title })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }

    return { modalShow, createEvent, deleteEvent, closeModal, modal, item, view }
  }
}
</script>
