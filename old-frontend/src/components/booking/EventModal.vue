<template>
  <b-modal
    id="eventModal"
    v-model="modalShow"
    size="lg"
    :title="modal.type === 'edit' ? $t(`components.bookings.item.modal.view.modal-title`) : $t(`components.bookings.item.modal.${modal.type}.modal-title`)"
    centered
    @hidden="closeModal"
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <label for="title">{{ $t(`components.bookings.item.modal.title`) }}</label>
        <b-form-input
          id="title"
          v-model="modal.title"
          :disabled="['view', 'edit'].includes(modal.type)"
          placeholder="Enter a title"
        />
      </b-col>
      <b-col
        cols="6"
        class="mt-2"
      >
        <label for="startDate">{{ $t(`components.bookings.item.modal.start-date`) }}*</label>
        <b-form-datepicker
          id="startDate"
          v-model="startDate"
          :disabled="['view', 'edit'].includes(modal.type)"
          type="date"
          :locale="$i18n.locale"
          :state="v$.startDate.$error ? false : null"
          @blur="v$.startDate.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.startDate.$error"
          id="startDateError"
        >
          {{ $t(`validations.${v$.startDate.$errors[0].$validator}`, { property: $t('components.bookings.item.modal.start-date') }) }}
        </b-form-invalid-feedback>
      </b-col>
      <b-col
        cols="6"
        class="mt-2"
      >
        <label for="startTime">{{ $t(`components.bookings.item.modal.start-time`) }}*</label>
        <b-form-input
          id="startTime"
          v-model="startTime"
          :disabled="['view', 'edit'].includes(modal.type)"
          type="time"
          :state="v$.startTime.$error ? false : null"
          @blur="v$.startTime.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.startTime.$error"
          id="startTimeError"
        >
          {{ $t(`validations.${v$.startTime.$errors[0].$validator}`, { property: $t('components.bookings.item.modal.start-time') }) }}
        </b-form-invalid-feedback>
      </b-col>
      <b-col
        cols="6"
        class="mt-2"
      >
        <label for="endDate">{{ $t(`components.bookings.item.modal.end-date`) }}*</label>
        <b-form-datepicker
          id="endDate"
          v-model="endDate"
          :disabled="['view', 'edit'].includes(modal.type)"
          type="date"
          :locale="$i18n.locale"
          :state="v$.endDate.$error ? false : null"
          @blur="v$.endDate.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.endDate.$error"
          id="endDateError"
        >
          {{ $t(`validations.${v$.endDate.$errors[0].$validator}`, { property: $t('components.bookings.item.modal.end-date') }) }}
        </b-form-invalid-feedback>
      </b-col>
      <b-col
        cols="6"
        class="mt-2"
      >
        <label for="endTime">{{ $t(`components.bookings.item.modal.end-time`) }}*</label>
        <b-form-input
          id="endTime"
          v-model="endTime"
          :disabled="['view', 'edit'].includes(modal.type)"
          type="time"
          :state="v$.endTime.$error ? false : null"
          @blur="v$.endTime.$touch"
        />
        <b-form-invalid-feedback
          v-if="v$.endTime.$error"
          id="endTimeError"
        >
          {{ $t(`validations.${v$.endTime.$errors[0].$validator}`, { property: $t('components.bookings.item.modal.end-time') }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          v-if="modal.type === 'edit'"
          squared
          class="float-left"
          variant="outline-danger"
          @click="deleteEvent"
        >
          {{ $t(`components.bookings.item.modal.delete.button`) }}
        </b-button>
        <b-button
          v-if="modal.type === 'create'"
          squared
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
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
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
        type: value.type
      })
    })

    const startDate = computed({
      get: () => $store.getters.getBookingEventModal.startDate,
      set: (value) => {
        modal.value.startDate = value
        $store.commit('setBookingEventModal', modal.value)
      }
    })

    const startTime = computed({
      get: () => $store.getters.getBookingEventModal.startTime,
      set: (value) => {
        modal.value.startTime = value
        $store.commit('setBookingEventModal', modal.value)
      }
    })

    const endDate = computed({
      get: () => $store.getters.getBookingEventModal.endDate,
      set: (value) => {
        modal.value.endDate = value
        $store.commit('setBookingEventModal', modal.value)
      }
    })

    const endTime = computed({
      get: () => $store.getters.getBookingEventModal.endTime,
      set: (value) => {
        modal.value.endTime = value
        $store.commit('setBookingEventModal', modal.value)
      }
    })

    const v$ = useVuelidate({
      startDate: {
        required
      },
      startTime: {
        required
      },
      endDate: {
        required
      },
      endTime: {
        required
      }
    }, {
      startDate,
      startTime,
      endDate,
      endTime
    })

    const createEvent = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      const start = DateUtils.stringToDate(`${startDate.value} ${startTime.value}`)
      const end = DateUtils.stringToDate(`${endDate.value} ${endTime.value}`)
      if (start < new Date()) {
        $store.dispatch('showNotification', { message: i18n.t('components.bookings.errors.past-booking') })
        return
      } else if (end < start) {
        $store.dispatch('showNotification', { message: i18n.t('components.bookings.errors.end-before-start') })
        return
      } else if (DateUtils.getMinutesBetweenDates(start, end) < 5) {
        $store.dispatch('showNotification', { message: i18n.t('components.bookings.errors.minimum-time') })
        return
      }
      $store.dispatch('createEvent', {
        elementId: item.value.id,
        elementType: view.value.itemType,
        title: modal.value.title,
        start: `${startDate.value} ${startTime.value}`,
        end: `${endDate.value} ${endTime.value}`
      }).then(() => {
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
      v$.value.$reset()
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

    return {
      modalShow,
      createEvent,
      deleteEvent,
      closeModal,
      modal,
      item,
      view,
      startDate,
      startTime,
      endDate,
      endTime,
      v$
    }
  }
}
</script>
