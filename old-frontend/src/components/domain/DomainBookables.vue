<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
      <strong>{{ $t('forms.domain.bookables.title') }}</strong>
    </h4>
    {{ $t(`forms.domain.bookables.vgpus`) }}
    <v-select
      v-model="vgpus"
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
          id="vgpus"
          class="vs__search"
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
    <div
      v-if="v$.vgpus.$error"
      id="vgpusError"
      class="text-danger"
    >
      {{ $t(`validations.${v$.vgpus.$errors[0].$validator}`, { property: `${$t("forms.domain.bookables.vgpus")}` }) }}
    </div>
  </div>
</template>

<script>
import { computed, onMounted, watch } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
import { ErrorUtils } from '@/utils/errorUtils'
import i18n from '@/i18n'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const availableBookables = computed(() => $store.getters.getBookables)
    const domain = computed(() => $store.getters.getDomain)
    const gpuVideos = computed(() => domain.value.hardware.videos.includes('none'))
    const vgpus = computed({
      get: () => $store.getters.getDomain.reservables.vgpus || [],
      // Multi-select: a desktop may carry several vGPU profiles, each on a
      // distinct physical card. Store the full array of selected profile ids.
      set: (value) => {
        domain.value.reservables.vgpus = (value && value.length) ? value : []
        $store.commit('setDomain', domain.value)
      }
    })

    // All of a desktop's vGPUs must live on ONE hypervisor (a guest runs on a
    // single host). The API tags each profile with the anonymized hypervisor
    // groups that can host it (hypervisor_groups); two profiles are
    // co-selectable iff their groups intersect. Hard-restrict the choices to
    // those compatible with the current selection.
    const compatibleOptions = computed(() => {
      const all = (availableBookables.value && availableBookables.value.vgpus) || []
      const selected = vgpus.value || []
      if (!selected.length) return all
      let common = null
      all.filter(o => selected.includes(o.id)).forEach(o => {
        const g = new Set(o.hypervisor_groups || [])
        common = common === null ? g : new Set([...common].filter(x => g.has(x)))
      })
      if (common && common.size) {
        return all.filter(o => (o.hypervisor_groups || []).some(x => common.has(x)))
      }
      return all
    })

    // A server (anonymized hypervisor group) is "multi-socket" only if its cards
    // span >1 NUMA node. On single-socket servers (and all-in-one) no socket
    // layer is shown. numa_by_group keys on the same anonymized index.
    const serverIsMulti = (all, g) => {
      const nodes = new Set()
      all.forEach(o => ((o.numa_by_group || {})[String(g)] || []).forEach(n => nodes.add(n)))
      return nodes.size > 1
    }

    // Each reservable is listed ONCE, under its primary (lowest) server set and,
    // on a multi-socket server, its primary (lowest) socket — with header rows
    // separating server sets and NUMA sockets. The label notes any extra
    // sets/sockets it can also reach, so nothing is hidden.
    const groupedOptions = computed(() => {
      const all = compatibleOptions.value
      const items = all.map(o => {
        const groups = (o.hypervisor_groups || []).slice().sort((a, b) => a - b)
        const pg = groups.length ? groups[0] : 0
        const sockets = ((o.numa_by_group || {})[String(pg)] || []).slice().sort((a, b) => a - b)
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

    // Label: base name + extra server sets it can host on + NUMA sockets it can
    // reach (so a card usable on several sockets is visible under its primary one).
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

    // Performance hint when ≥2 profiles are selected: on the shared server, is
    // there a NUMA socket every selected profile has a card on? Green when yes
    // (engine will co-locate them), amber when only different sockets are
    // possible (still starts, slower cross-socket memory). Hidden otherwise.
    const numaHint = computed(() => {
      const all = (availableBookables.value && availableBookables.value.vgpus) || []
      const selected = vgpus.value || []
      const chosen = all.filter(o => selected.includes(o.id))
      if (chosen.length < 2) return null
      let common = null
      chosen.forEach(o => {
        const g = new Set(o.hypervisor_groups || [])
        common = common === null ? g : new Set([...common].filter(x => g.has(x)))
      })
      if (!common || !common.size) return null
      let sawMulti = false
      for (const g of common) {
        if (!serverIsMulti(all, g)) continue
        sawMulti = true
        let nodes = null
        chosen.forEach(o => {
          const s = new Set((o.numa_by_group || {})[String(g)] || [])
          nodes = nodes === null ? s : new Set([...nodes].filter(x => s.has(x)))
        })
        if (nodes && nodes.size) return { ok: true, node: [...nodes].sort((a, b) => a - b)[0] }
      }
      return sawMulti ? { ok: false } : null
    })

    // When not selecting a GPU (empty or the 'None' option), set video to default
    watch(vgpus, (newVal, prevVal) => {
      const noGpu = !vgpus.value.length || vgpus.value.includes('None')
      if (noGpu && gpuVideos.value) {
        ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.video-default'), '', true, 5000)
        $store.dispatch('changeVideos', ['default'])
      }
    })

    onMounted(() => {
      $store.dispatch('fetchBookables')
    })
    return {
      availableBookables,
      groupedOptions,
      numaHint,
      vgpus,
      v$: useVuelidate({
        vgpus: {
          required
        }
      }, { vgpus })
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
