<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
      <strong>{{ $t('forms.domain.bookables.title') }}</strong>
    </h4>
    {{ $t(`forms.domain.bookables.vgpus`) }}
    <v-select
      v-model="vgpus"
      :options="availableBookables.vgpus"
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
      get: () => $store.getters.getDomain.reservables.vgpus,
      set: (value) => {
        domain.value.reservables.vgpus = value ? [value] : []
        $store.commit('setDomain', domain.value)
      }
    })

    // When not selecting a GPU, set the video to default
    watch(vgpus, (newVal, prevVal) => {
      if (vgpus.value[0] === 'None' && gpuVideos.value) {
        ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.video-default'), '', true, 5000)
        $store.dispatch('changeVideos', ['default'])
      }
    })

    onMounted(() => {
      $store.dispatch('fetchBookables')
    })
    return {
      availableBookables,
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
