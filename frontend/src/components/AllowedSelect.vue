<template>
  <div>
    <IsardSearchSelect
      @search="fetchAllowedTerm"
      @updateSelected="updateSelected"
      :options="options"
      :closeOnSelect="false"
      :deselectFromDropdown="true"
      :placeholder="placeholder"
      :disabled="disabled"
      :reset="reset"
    />
  </div>
</template>
<script>
import IsardSearchSelect from '@/components/shared/IsardSearchSelect.vue'
import { map } from 'lodash'

export default {
  components: {
    IsardSearchSelect
  },
  props: {
    placeholder: {
      type: String,
      required: false,
      default: ''
    },
    table: {
      type: String,
      required: true
    },
    options: {
      type: Array,
      required: true,
      default: () => { return [] }
    },
    disabled: {
      type: Boolean,
      required: false,
      default: false
    },
    reset: {
      type: Boolean,
      required: false,
      default: false
    }
  },
  setup (props, context) {
    const $store = context.root.$store

    function fetchAllowedTerm (data) {
      $store.dispatch('fetchAllowedTerm', { table: props.table, term: data.search }).then(() => data.loading(false))
    }
    function updateSelected (selected) {
      const selectedIds = map(selected, 'id')
      $store.dispatch('updateSelected', { table: props.table, selected: selectedIds })
    }

    return {
      fetchAllowedTerm,
      updateSelected
    }
  }
}
</script>
