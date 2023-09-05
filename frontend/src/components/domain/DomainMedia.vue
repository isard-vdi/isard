<template>
  <div>
    <!-- Title -->
    <h4 class="my-4">
      <strong>{{ $t('forms.domain.media.title') }}</strong>
    </h4>
    <b-row>
      <b-col
        cols="12"
        xl="6"
        class="mb-2"
      >
        {{ $t(`forms.domain.media.isos`) }}
        <IsardSearchSelect
          :options="isos"
          :close-on-select="false"
          :deselect-from-dropdown="true"
          :selected-values="selectedIsos"
          :placeholder="$t(`forms.domain.media.placeholder`)"
          @search="fetchIsoAllowedTerm"
          @updateSelected="updateIsosSelected"
        />
      </b-col>
      <b-col
        cols="12"
        xl="6"
        class="mb-2"
      >
        {{ $t(`forms.domain.media.floppies`) }}
        <IsardSearchSelect
          :options="floppies"
          :close-on-select="false"
          :deselect-from-dropdown="true"
          :selected-values="selectedFloppies"
          :placeholder="$t(`forms.domain.media.placeholder`)"
          @search="fetchFloppyAllowedTerm"
          @updateSelected="updateFloppiesSelected"
        />
      </b-col>
    </b-row>
  </div>
</template>

<script>
import IsardSearchSelect from '@/components/shared/IsardSearchSelect.vue'
import { computed } from '@vue/composition-api'

export default {
  components: {
    IsardSearchSelect
  },
  setup (props, context) {
    const $store = context.root.$store
    const isos = computed(() => $store.getters.getIsos)
    const floppies = computed(() => $store.getters.getFloppies)
    const selectedIsos = computed(() => $store.getters.getDomain.hardware.isos)
    const selectedFloppies = computed(() => $store.getters.getDomain.hardware.floppies)

    const fetchIsoAllowedTerm = (data) => {
      $store.dispatch('fetchAllowedTerm', { table: 'media', term: data.search, kind: 'isos' }).then(() => data.loading(false))
    }

    const fetchFloppyAllowedTerm = (data) => {
      $store.dispatch('fetchAllowedTerm', { table: 'media', term: data.search, kind: 'floppies' }).then(() => data.loading(false))
    }

    const updateIsosSelected = (selectedIsos) => {
      $store.dispatch('updateSelected', { table: 'isos', selected: selectedIsos })
    }
    const updateFloppiesSelected = (selectedFloppies) => {
      $store.dispatch('updateSelected', { table: 'floppies', selected: selectedFloppies })
    }

    return {
      isos,
      floppies,
      selectedIsos,
      selectedFloppies,
      fetchIsoAllowedTerm,
      fetchFloppyAllowedTerm,
      updateIsosSelected,
      updateFloppiesSelected
    }
  }
}
</script>
