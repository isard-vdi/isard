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
          :options="groupedOptions"
          :selectable="option => !option.header"
          label="name"
          :reduce="element => element.id"
        >
          <template #option="option">
            <span
              v-if="option.header"
              :class="option.level === 1 ? 'numa-grp-socket' : 'numa-grp-server'"
            >{{ option.name }}</span>
            <span
              v-else
              :class="{ 'pl-3': option.numaIndent }"
            >{{ option.name }}</span>
          </template>
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
        <!-- NUMA same-socket performance hint (informational; never restricts start) -->
        <div
          v-if="numaHint"
          :class="['mt-1', 'small', numaHint.ok ? 'text-success' : 'text-warning']"
        >
          <i :class="numaHint.ok ? 'fa fa-check-circle' : 'fa fa-exclamation-triangle'" />
          <span v-if="numaHint.ok">{{ $t('forms.domain.bookables.numa-same-socket', { node: numaHint.node }) }}</span>
          <span v-else>{{ $t('forms.domain.bookables.numa-diff-socket') }}</span>
        </div>
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
import i18n from '@/i18n'

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
    // the current selection (same hypervisorGroups intersection rule as the
    // desktop editor). See DomainBookables.vue.
    const compatibleOptions = computed(() => {
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

    // A server (anonymized hypervisor group) is multi-socket only if its cards
    // span >1 NUMA node; single-socket / all-in-one show no socket layer.
    const serverIsMulti = (all, g) => {
      const nodes = new Set()
      all.forEach(o => ((o.numaByGroup || {})[String(g)] || []).forEach(n => nodes.add(n)))
      return nodes.size > 1
    }

    const optionLabel = (it, multi) => {
      let label = it.o.name
      if (it.groups.length > 1) {
        label += ` · ${i18n.t('forms.domain.bookables.sets')} ${it.groups.join('/')}`
      }
      if (multi && it.sockets.length) {
        label += ` · NUMA ${it.sockets.join('/')}`
      }
      return label
    }

    // Group server → NUMA socket; each reservable listed once under its primary
    // group, header rows in between (only on multi-socket / multi-server).
    const groupedOptions = computed(() => {
      const all = compatibleOptions.value
      const items = all.map(o => {
        const groups = (o.hypervisorGroups || []).slice().sort((a, b) => a - b)
        const pg = groups.length ? groups[0] : 0
        const sockets = ((o.numaByGroup || {})[String(pg)] || []).slice().sort((a, b) => a - b)
        const ps = sockets.length ? sockets[0] : -1
        return { o, pg, ps, sockets, groups }
      }).sort((a, b) => a.pg - b.pg || a.ps - b.ps || (a.o.name > b.o.name ? 1 : -1))

      const rows = []
      let curG = null
      let curS = null
      const multiServer = items.length && new Set(items.map(it => it.pg)).size > 1
      items.forEach(it => {
        const multi = serverIsMulti(all, it.pg)
        if (it.pg !== curG) {
          curG = it.pg
          curS = null
          if (multiServer || multi) {
            rows.push({ header: true, level: 0, name: i18n.t('forms.domain.bookables.server-set', { n: it.pg }) })
          }
        }
        if (multi && it.ps !== curS) {
          curS = it.ps
          rows.push({
            header: true,
            level: 1,
            name: it.ps >= 0
              ? i18n.t('forms.domain.bookables.numa-socket', { n: it.ps })
              : i18n.t('forms.domain.bookables.numa-socket-unknown')
          })
        }
        rows.push({ ...it.o, name: optionLabel(it, multi), numaIndent: multi })
      })
      return rows
    })

    // Same-socket performance hint when ≥2 profiles selected.
    const numaHint = computed(() => {
      const all = modal.value.data.availableProfiles || []
      const selected = profiles.value || []
      const chosen = all.filter(o => selected.includes(o.id))
      if (chosen.length < 2) return null
      let common = null
      chosen.forEach(o => {
        const g = new Set(o.hypervisorGroups || [])
        common = common === null ? g : new Set([...common].filter(x => g.has(x)))
      })
      if (!common || !common.size) return null
      let sawMulti = false
      for (const g of common) {
        if (!serverIsMulti(all, g)) continue
        sawMulti = true
        let nodes = null
        chosen.forEach(o => {
          const s = new Set((o.numaByGroup || {})[String(g)] || [])
          nodes = nodes === null ? s : new Set([...nodes].filter(x => s.has(x)))
        })
        if (nodes && nodes.size) return { ok: true, node: [...nodes].sort((a, b) => a - b)[0] }
      }
      return sawMulti ? { ok: false } : null
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
      groupedOptions,
      numaHint,
      availableTimes
    }
  }
}
</script>

<style scoped>
.numa-grp-server {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.8em;
  color: #555;
}
.numa-grp-socket {
  font-weight: 600;
  padding-left: 1rem;
  font-size: 0.85em;
  color: #777;
}
</style>
