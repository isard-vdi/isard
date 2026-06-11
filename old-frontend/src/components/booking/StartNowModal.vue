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
        <label for="profiles">{{ $t(`components.start-now-modal.profiles`) }}*</label>
        <!-- A desktop may carry several vGPU profiles, all on ONE hypervisor.
             Pick the set to start now; options are restricted to profiles that
             can share a host with the current selection. -->
        <v-select
          v-model="profiles"
          multiple
          :close-on-select="false"
          :options="bookableOptions"
          label="name"
          :reduce="element => element.id"
        >
          <template #search="{ attributes, events }">
            <input
              id="profiles"
              class="vs__search"
              :required="!profiles.length"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <b-form-invalid-feedback
          v-if="v$.profiles.$error"
          id="profilesError"
          :force-show="true"
        >
          {{ $t(`validations.${v$.profiles.$errors[0].$validator}`, { property: $t('components.start-now-modal.profiles') }) }}
        </b-form-invalid-feedback>
      </b-col>
      <b-col
        :cols="modal.showProfileDropdown ? 6 : 12"
        class="mt-2"
      >
        <label for="endDate">{{ $t(`components.start-now-modal.end-time`) }}</label>
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
          {{ $t(`validations.${v$.endDate.$errors[0].$validator}`, { property: $t('components.start-now-modal.end-time') }) }}
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
import { computed } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, requiredIf } from '@vuelidate/validators'
import { DateUtils } from '@/utils/dateUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const item = computed(() => $store.getters.getBookingItem)
    const modal = computed(() => $store.getters.getStartNowModal)

    const profiles = computed({
      get: () => $store.getters.getStartNowModal.selected.profiles || [],
      set: (value) => {
        modal.value.selected.profiles = value || []
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

    // Restrict the choices to profiles co-locatable on a single hypervisor with
    // the current selection (same hypervisor_groups intersection rule as the
    // desktop editor). See DomainBookables.vue.
    const bookableOptions = computed(() => {
      const all = modal.value.data.availableProfiles || []
      const selected = profiles.value || []
      if (!selected.length) return all
      let common = null
      all.filter(o => selected.includes(o.id)).forEach(o => {
        const g = new Set(o.hypervisorGroups || [])
        common = common === null ? g : new Set([...common].filter(x => g.has(x)))
      })
      if (common && common.size) {
        return all.filter(o => (o.hypervisorGroups || []).some(x => common.has(x)))
      }
      return all
    })

    // The booking can only run as long as the EARLIEST window among the selected
    // profiles (the bottleneck). Non-recovery uses the desktop's single window.
    const endLimit = computed(() => {
      if (!modal.value.showProfileDropdown) return modal.value.data.maxBookingDate
      const selected = (modal.value.data.availableProfiles || []).filter(p => (profiles.value || []).includes(p.id))
      if (!selected.length) return null
      return selected.reduce((min, p) => (!min || p.maxBookingDate < min) ? p.maxBookingDate : min, null)
    })

    const availableTimes = computed(() => {
      if (!endLimit.value) return []
      return DateUtils.breakTimeInChunks(
        DateUtils.dateToMoment(new Date()),
        DateUtils.stringToDate(DateUtils.utcToLocalTime(endLimit.value)),
        30,
        'minutes'
      ).map((time) => {
        return { text: DateUtils.formatAsTime(time), value: time }
      })
    })

    const v$ = useVuelidate({
      profiles: {
        required: requiredIf(() => modal.value.showProfileDropdown)
      },
      endDate: {
        required
      }
    }, {
      profiles,
      endDate
    })

    const startDesktop = () => {
      v$.value.$touch()
      if (v$.value.$invalid) {
        return
      }
      if (modal.value.showProfileDropdown) {
        // Recovery: rebuild the desktop's GPU set from the currently-available,
        // co-locatable profiles the user picked, then book now.
        const data = {
          id: item.value.id,
          reservables: { vgpus: profiles.value }
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
      v$.value.$reset()
      $store.dispatch('resetStartNowModal')
    }

    return {
      startDesktop,
      closeModal,
      modal,
      profiles,
      endDate,
      v$,
      bookableOptions,
      availableTimes
    }
  }
}
</script>
