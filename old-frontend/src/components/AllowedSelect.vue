<template>
  <div>
    <IsardSearchSelect
      :options="options"
      :close-on-select="false"
      :deselect-from-dropdown="true"
      :placeholder="placeholder"
      :disabled="disabled"
      :selected-values="selectedValues"
      :role="role"
      @search="fetchAllowedTerm"
      @updateSelected="updateSelected"
    />
  </div>
</template>
<script>
import IsardSearchSelect from '@/components/shared/IsardSearchSelect.vue'

export default {
  components: {
    IsardSearchSelect
  },
  props: {
    selectedValues: {
      type: Array,
      required: false,
      default: () => { return [] }
    },
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
    role: {
      type: String,
      required: false,
      default: ''
    }
  },
  setup (props, context) {
    const $store = context.root.$store

    const fetchAllowedTerm = (data) => {
      $store.dispatch('fetchAllowedTerm', { table: props.table, term: data.search, exclude_role: props.role }).then(() => data.loading(false))
    }

    const updateSelected = (selected) => {
      $store.dispatch('updateSelected', { table: props.table, selected: selected })
    }

    return {
      fetchAllowedTerm,
      updateSelected
    }
  }
}
</script>
