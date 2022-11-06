<template>
  <b-modal
    id="eventModal"
    v-model="modalShow"
    size="lg"
    :title="$t(`components.bookings.item.modal.${modal.type}.modal-title`)"
    centered
    @hidden="closeModal"
  >
    <b-form :disabled="modal.type == 'view'">
      <b-row class="ml-2 mr-2">
        <b-col
          cols="6"
          class="mt-2"
        >
          <label for="eventStartDate">{{ $t(`components.bookings.item.modal.start-date`) }}*</label>
          <b-form-datepicker
            id="eventStartDate"
            v-model="modal.startDate"
            :disabled="modal.type == 'view'"
            type="date"
            :locale="$i18n.locale"
          />
        </b-col>
        <b-col
          cols="6"
          class="mt-2"
        >
          <label for="eventStartTime">{{ $t(`components.bookings.item.modal.start-time`) }}*</label>
          <b-form-input
            id="eventStartTime"
            v-model="modal.startTime"
            :disabled="modal.type == 'view'"
            type="time"
          />
        </b-col>
        <b-col
          cols="6"
          class="mt-2"
        >
          <label for="eventEndDate">{{ $t(`components.bookings.item.modal.end-date`) }}*</label>
          <b-form-datepicker
            id="eventEndDate"
            v-model="modal.endDate"
            :disabled="modal.type == 'view'"
            type="date"
            :locale="$i18n.locale"
          />
        </b-col>
        <b-col
          cols="6"
          class="mt-2"
        >
          <label for="eventEndTime">{{ $t(`components.bookings.item.modal.end-time`) }}*</label>
          <b-form-input
            id="eventEndTime"
            v-model="modal.endTime"
            :disabled="modal.type == 'view'"
            type="time"
          />
        </b-col>
        <b-col
          cols="12"
          class="mt-2"
        >
          <label for="eventSubitem">{{ $t(`components.bookings.item.modal.profile`) }}*</label>
          <b-form-select
            id="eventSubitem"
            v-model="modal.subitemId"
            :disabled="modal.type == 'view'"
            :options="optionSubitems"
          >
            <template #first>
              <b-form-select-option
                :value="null"
                disabled
              >
                {{ $t(`components.bookings.item.modal.select-profile`) }}
              </b-form-select-option>
            </template>
          </b-form-select>
        </b-col>
      </b-row>
    </b-form>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          v-if="modal.type === 'edit'"
          squared
          class="float-left"
          variant="outline-danger"
          @click="deleteEvent"
        >
          Delete
        </b-button>
        <b-button
          v-if="modal.type === 'create'"
          squared
          variant="primary"
          class="float-right"
          @click="createEvent"
        >
          Create event
        </b-button>
        <!-- <b-button
          v-if="modal.type === 'edit'"
          squared
          variant="primary"
          class="float-right"
          @click="editEvent"
        >
          Save changes
        </b-button> -->
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'
import i18n from '@/i18n'
import { PlanningUtils } from '@/utils/planningUtils'

export default {
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
  },
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
  }
}
</script>
