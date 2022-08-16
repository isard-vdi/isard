<template>
  <div>
    <!-- Title -->
    <h4 class="my-4">
      <strong>{{ $t('forms.domain.bookables.title') }}</strong>
    </h4>
    {{ $t(`forms.domain.bookables.vgpus`) }}
    <v-select
      v-model="vgpus"
      :options="availableBookables.vgpus"
      label="name"
      :reduce="element => element.id"
    />
  </div>
</template>

<script>
import { computed, onMounted } from '@vue/composition-api'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const availableBookables = computed(() => $store.getters.getBookables)
    const domain = computed(() => $store.getters.getDomain)
    const vgpus = computed({
      get: () => $store.getters.getDomain.reservables.vgpus,
      set: (value) => {
        domain.value.reservables.vgpus = [value]
        $store.commit('setDomain', domain.value)
      }
    })

    onMounted(() => {
      $store.dispatch('fetchBookables')
    })
    return {
      availableBookables,
      vgpus
    }
  }
}
</script>
