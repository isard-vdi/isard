<template>
  <b-row class="mt-1">
    <b-col
      cols="2"
      class="mt-1"
    >
      <label
        for="filterInput"
        class="ml-2 text-medium-gray"
      >{{ $t('components.desktop-cards.filter-label') }}</label>
    </b-col>
    <b-col cols="10">
      <b-input-group size="sm">
        <b-form-input
          id="filterInput"
          v-model="filterText"
        />
        <b-input-group-append>
          <b-button
            :disabled="!filterText"
            @click="filterText = ''"
          >
            {{ $t('forms.clear') }}
          </b-button>
        </b-input-group-append>
      </b-input-group>
    </b-col>
  </b-row>
</template>

<script>
import { ref, watch } from '@vue/composition-api'
import { mapGetters } from 'vuex'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const filterText = ref('')

    function updateFilter (currentValue) {
      $store.dispatch('updateDesktopsFilter', { filter: currentValue })
    }

    watch(filterText, (currentValue, _) => {
      updateFilter(currentValue)
    })

    watch(() => context.root.$route, () => {
      filterText.value = ''
    }, { immediate: true })

    return {
      filterText
    }
  },
  computed: {
    ...mapGetters(['getDesktopsFilter'])
  },
  mounted () {
    this.filterText = this.getDesktopsFilter
  }
}
</script>
