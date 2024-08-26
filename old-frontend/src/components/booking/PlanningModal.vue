<template>
  <b-modal
    id="eventModal"
    v-model="modalShow"
    size="lg"
    :title="modal.type === 'edit' ? $t(`components.bookings.item.modal.view.modal-title`) : $t(`components.bookings.item.modal.${modal.type}.modal-title`)"
    centered
    @hidden="closeModal"
  >
    <b-form :disabled="modal.type == 'view'">
      <b-row class="ml-2 mr-2">
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
        <b-col
          cols="12"
          class="mt-2"
        >
          <label for="eventSubitem">{{ $t(`components.bookings.item.modal.profile`) }}*</label>
          <b-form-select
            id="subitemId"
            v-model="subitemId"
            :disabled="['view', 'edit'].includes(modal.type)"
            :options="optionSubitems"
            :state="v$.subitemId.$error ? false : null"
            @blur="v$.subitemId.$touch"
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
          <b-form-invalid-feedback
            v-if="v$.subitemId.$error"
            id="subitemIdError"
          >
            {{ $t(`validations.${v$.subitemId.$errors[0].$validator}`, { property: $t('components.bookings.item.modal.profile') }) }}
          </b-form-invalid-feedback>
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
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'

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
        type: value.type
      })
    })

    const startDate = computed({
      get: () => $store.getters.getPlanningEventModal.startDate,
      set: (value) => {
        modal.value.startDate = value
        $store.commit('setPlanningEventModal', modal.value)
      }
    })

    const startTime = computed({
      get: () => $store.getters.getPlanningEventModal.startTime,
      set: (value) => {
        modal.value.startTime = value
        $store.commit('setPlanningEventModal', modal.value)
      }
    })

    const endDate = computed({
      get: () => $store.getters.getPlanningEventModal.endDate,
      set: (value) => {
        modal.value.endDate = value
        $store.commit('setPlanningEventModal', modal.value)
      }
    })

    const endTime = computed({
      get: () => $store.getters.getPlanningEventModal.endTime,
      set: (value) => {
        modal.value.endTime = value
        $store.commit('setPlanningEventModal', modal.value)
      }
    })

    const subitemId = computed({
      get: () => $store.getters.getPlanningEventModal.subitemId,
      set: (value) => {
        modal.value.subitemId = value
        $store.commit('setPlanningEventModal', modal.value)
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
      },
      subitemId: {
        required
      }
    }, {
      startDate,
      startTime,
      endDate,
      endTime,
      subitemId
    })

    const createEvent = () => {
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      const eventData = {
        type: type.value,
        itemId: item.value,
        subitemId: subitemId.value,
        start: `${startDate.value} ${startTime.value}`,
        end: `${endDate.value} ${endTime.value}`
      }
      $store.dispatch('createPlanningEvent', eventData)
    }

    const editEvent = () => {
      const eventData = {
        id: modal.value.id,
        subitemId: modal.value.subitemId,
        start: `${modal.value.startDate} ${modal.value.startTime}`,
        end: `${modal.value.endDate} ${modal.value.endTime}`
      }
      $store.dispatch('editPlanningEvent', eventData)
    }

    const closeModal = () => {
      v$.value.$reset()
      $store.dispatch('resetPlanningModalData')
      $store.dispatch('showPlanningModal', false)
    }

    return {
      modalShow,
      createEvent,
      editEvent,
      closeModal,
      modal,
      optionSubitems,
      startDate,
      startTime,
      endDate,
      endTime,
      subitemId,
      v$
    }
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
