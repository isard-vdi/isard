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
      :options="bookableOptions"
      label="name"
      :reduce="element => element.id"
    >
      <template #search="{ attributes, events }">
        <input
          id="vgpus"
          class="vs__search"
          v-bind="attributes"
          v-on="events"
        >
      </template>
    </v-select>
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
    // those compatible with the current selection, and show the (nameless)
    // group so the user sees the compatible sets.
    const groupedLabel = (o) => {
      const g = o.hypervisor_groups || []
      if (!g.length) return o.name
      return `${o.name} · ${g.length > 1 ? 'sets' : 'set'} ${g.join('/')}`
    }
    const bookableOptions = computed(() => {
      const all = (availableBookables.value && availableBookables.value.vgpus) || []
      const selected = vgpus.value || []
      let list = all
      if (selected.length) {
        let common = null
        all.filter(o => selected.includes(o.id)).forEach(o => {
          const g = new Set(o.hypervisor_groups || [])
          common = common === null ? g : new Set([...common].filter(x => g.has(x)))
        })
        if (common && common.size) {
          list = all.filter(o => (o.hypervisor_groups || []).some(x => common.has(x)))
        }
      }
      return list.map(o => ({ ...o, name: groupedLabel(o) }))
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
      bookableOptions,
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
