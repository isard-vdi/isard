<template>
  <b-modal
    id="eventModal"
    size="lg"
    :title="$t(`components.bookings.item.modal.${modal.type}.modal-title`)"
    v-model="modalShow"
    @hidden="closeModal"
    centered
  >
    <b-form :disabled="modal.type == 'view'">
      <b-row class="ml-2 mr-2">
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
        <b-col cols="12" class="mt-2">
          <label for="eventSubitem">{{ $t(`components.bookings.item.modal.profile`) }}*</label>
          <b-form-select :disabled="modal.type == 'view'" id="eventSubitem" v-model="modal.subitemId" :options="optionSubitems">
            <template #first>
              <b-form-select-option :value="null" disabled>{{ $t(`components.bookings.item.modal.select-profile`) }}</b-form-select-option>
            </template>
          </b-form-select>
        </b-col>
      </b-row>
    </b-form>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          class="float-left"
          variant="outline-danger"
          v-if="modal.type === 'edit'"
          @click="deleteEvent"
        >
          Delete
        </b-button>
        <b-button
          squared
          v-if="modal.type === 'create'"
          variant="primary"
          class="float-right"
          @click="createEvent"
        >
          Create event
        </b-button>
        <b-button
          v-if="modal.type === 'edit'"
          squared
          variant="primary"
          class="float-right"
          @click="editEvent"
        >
          Save changes
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'
import i18n from '@/i18n'
import { PlanningUtils } from '@/utils/planningUtils'

export default {
  methods: {
    deleteEvent (toast) {
      this.$snotify.clear()

      const yesAction = () => {
        toast.valid = true // default value
        this.$snotify.remove(toast.id)
        this.$store.dispatch('deletePlanningEvent', {
          id: this.modal.id
        })
      }

      const noAction = (toast) => {
        this.$snotify.remove(toast.id) // default
      }

      this.$snotify.prompt(`${i18n.t('messages.confirmation.delete-event', { name: this.modal.subitemId })}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}`, action: noAction }
        ],
        placeholder: ''
      })
    }
  },
  setup (_, context) {
    const $store = context.root.$store

    const type = computed(() => $store.getters.getPlanningSelectedReservableType)
    const item = computed(() => $store.getters.getPlanningSelectedReservableItem)
    const subitems = computed(() => $store.getters.getPlanningReservableSubitems || [])
    const optionSubitems = ref([])

    const modalShow = computed({
      get: () => $store.getters.getPlanningModalShow,
      set: (value) => $store.commit('setPlanningModalShow', value)
    })

    watch(modalShow, (modalShow, prevVal) => {
      if (modalShow) {
        $store.dispatch('fetchReservableSubitems', { itemType: type.value, itemId: item.value }).then(() => {
          optionSubitems.value = subitems.value.map(item => {
            return {
              value: item.id,
              text: item.name
            }
          })
        })
      }
    }, { immediate: true })

    const modal = computed({
      get: () => $store.getters.getPlanningEventModal,
      set: (value) => $store.commit('setPlanningEventModal', {
        type: value.type,
        startDate: value.startDate,
        startTime: value.startTime,
        endDate: value.endDate,
        endTime: value.endTime
      })
    })

    const createEvent = () => {
      const eventData = {
        type: type.value,
        itemId: item.value,
        subitemId: modal.value.subitemId,
        date: `${modal.value.startDate} ${modal.value.startTime}`,
        end: `${modal.value.endDate} ${modal.value.endTime}`
      }
      if (PlanningUtils.checkModalData(eventData)) {
        $store.dispatch('createPlanningEvent', eventData)
      } else {
        $store.dispatch('showNotification', { message: i18n.t('messages.info.missing-data') })
      }
    }

    const editEvent = () => {
      const eventData = {
        id: modal.value.id,
        subitemId: modal.value.subitemId,
        date: `${modal.value.startDate} ${modal.value.startTime}`,
        end: `${modal.value.endDate} ${modal.value.endTime}`
      }
      if (PlanningUtils.checkModalData(eventData)) {
        $store.dispatch('editPlanningEvent', eventData)
      } else {
        $store.dispatch('showNotification', { message: i18n.t('messages.info.missing-data') })
      }
    }

    const closeModal = () => {
      $store.dispatch('resetPlanningModalData')
      $store.dispatch('showPlanningModal', false)
    }

    return { modalShow, createEvent, editEvent, closeModal, modal, optionSubitems }
  }
}
</script>
