<template>
  <b-modal
    id="startNowModal"
    v-model="modal.show"
    :size="modal.showProfileDropdown ? 'lg' : 'md'"
    :title="$t(`components.start-now-modal.title`)"
    centered
    @hidden="closeModal"
  >
    <b-row class="ml-2 mr-2">
      <b-col
        v-if="modal.showProfileDropdown"
        cols="6"
        class="mt-2"
      >
        <label for="profile">{{ $t(`components.start-now-modal.profile`) }}*</label>
        <b-form-select
          id="profile"
          v-model="profile"
          :options="modal.data.availableProfiles"
          :state="v$.profile.$error ? false : null"
          @blur="v$.profile.$touch"
        >
          <template #first>
            <b-form-select-option
              :value="null"
              disabled
            >
              {{ $t(`components.start-now-modal.select-profile`) }}
            </b-form-select-option>
          </template>
        </b-form-select>
        <b-form-invalid-feedback
          v-if="v$.profile.$error"
          id="profileError"
        >
          {{ $t(`validations.${v$.profile.$errors[0].$validator}`, { property: $t('components.start-now-modal.profile') }) }}
        </b-form-invalid-feedback>
      </b-col>
      <b-col
        :cols="modal.showProfileDropdown ? 6 : 12"
        class="mt-2"
      >
        <label for="endDate">{{ $t(`components.start-now-modal.end-date`) }}*</label>
        <b-form-select
          id="endDate"
          v-model="endDate"
          :options="availableTimes"
          :state="v$.endDate.$error ? false : null"
          @blur="v$.endDate.$touch"
        >
          <template #first>
            <b-form-select-option
              :value="null"
              disabled
            >
              {{ $t(`components.start-now-modal.select-end-date`) }}
            </b-form-select-option>
          </template>
        </b-form-select>
        <b-form-invalid-feedback
          v-if="v$.endDate.$error"
          id="endDateError"
        >
          {{ $t(`validations.${v$.endDate.$errors[0].$validator}`, { property: $t('components.start-now-modal.end-date') }) }}
        </b-form-invalid-feedback>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          variant="primary"
          class="float-right"
          @click="startDesktop"
        >
          {{ $t(`components.start-now-modal.button`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { ref, computed, watch } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
import { DateUtils } from '@/utils/dateUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const availableTimes = ref([])
    const item = computed(() => $store.getters.getBookingItem)

    const modal = computed(() => $store.getters.getStartNowModal)

    const profile = computed({
      get: () => $store.getters.getStartNowModal.selected.profile,
      set: (value) => {
        modal.value.selected.profile = value
        $store.commit('setStartNowModal', modal.value)
      }
    })

    const endDate = computed({
      get: () => $store.getters.getStartNowModal.selected.endDate,
      set: (value) => {
        modal.value.selected.endDate = value
        $store.commit('setStartNowModal', modal.value)
      }
    })

    watch(profile, (newVal, prevVal) => {
      if (newVal) {
        const timeChunks = DateUtils.breakTimeInChunks(DateUtils.dateToMoment(new Date()), DateUtils.stringToDate(DateUtils.utcToLocalTime(newVal.maxBookingDate)), 30, 'minutes')
        availableTimes.value = timeChunks.map((time) => {
          return {
            text: DateUtils.formatAsTime(time),
            value: time
          }
        })
      }
    }, { immediate: true })

    const v$ = useVuelidate({
      profile: {
        required
      },
      endDate: {
        required
      }
    }, {
      profile,
      endDate
    })

    const startDesktop = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      if (modal.value.showProfileDropdown) {
        const data = {
          id: item.value.id,
          reservables: { vgpus: [profile.value.id] }
        }
        $store.dispatch('editDesktopReservables', data).then(() => {
          createEventNow()
        })
      } else {
        createEventNow()
      }
    }

    const createEventNow = () => {
      $store.dispatch('createEventNow', {
        elementId: item.value.id,
        elementType: 'desktop',
        start: DateUtils.localTimeToUtc(DateUtils.dateToMoment(new Date())),
        end: modal.value.selected.endDate
      }).then(() => {
        $store.dispatch('changeDesktopStatus', { action: modal.value.selected.action, desktopId: item.value.id })
        closeModal()
      })
    }

    const closeModal = () => {
      $store.dispatch('resetStartNowModal')
      availableTimes.value = []
    }

    return {
      startDesktop,
      closeModal,
      modal,
      profile,
      endDate,
      v$,
      availableTimes
    }
  }
}
</script>
