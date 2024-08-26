<template>
  <v-select
    multiple
    :placeholder="placeholder"
    :options="options"
    :disabled="disabled"
    :close-on-select="closeOnSelect"
    :deselect-from-dropdown="deselectFromDropdown"
    :loading="false"
    :value="selectedValues"
    @search="fetch"
    @input="setSelected"
  >
    <template #option="option">
      <input
        type="checkbox"
        :checked="selectedValues && selectedValues.includes(selectedValues.find(el => el.id === option.id))"
      >
      {{ option.label }}
    </template>
    <template #spinner="{ loading }">
      <b-spinner
        v-if="loading"
        variant="info"
        small
        label="Spinning"
      />
    </template>
    <!-- eslint-disable-next-line vue/no-unused-vars  -->
    <template #no-options="{ search, searching, loading }">
      {{ $t('components.select-search.empty') }}
    </template>
  </v-select>
</template>
<script>

export default {
  props: {
    selectedValues: {
      type: Array,
      required: false,
      default: () => { return [] }
    },
    options: {
      type: Array,
      required: false,
      default: () => { return [] }
    },
    closeOnSelect: {
      type: Boolean,
      required: false,
      default: false
    },
    deselectFromDropdown: {
      type: Boolean,
      required: false,
      default: false
    },
    disabled: {
      type: Boolean,
      required: false,
      default: false
    },
    placeholder: {
      type: String,
      required: false,
      default: ''
    }
  },
  setup (props, { emit }) {
    const fetch = (search, loading) => {
      if (!/[`!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?~]/.test(search) && search.length >= 2) {
        loading(true)
        emit('search', { search, loading })
      }
    }

    const setSelected = (value) => {
      emit('updateSelected', value)
    }

    return {
      fetch,
      setSelected
    }
  }
}
</script>
<style scoped>
:root {
  --vs-colors--lightest: rgba(60, 60, 60, 0.26);
  --vs-colors--light: rgba(60, 60, 60, 0.5);
  --vs-colors--dark: #333;
  --vs-colors--darkest: rgba(0, 0, 0, 0.15);

  /* Search Input */
  --vs-search-input-color: inherit;
  --vs-search-input-placeholder-color: inherit;

  /* Font */
  --vs-font-size: 1rem;
  --vs-line-height: 1.4;

  /* Disabled State */
  --vs-state-disabled-bg: rgb(248, 248, 248);
  --vs-state-disabled-color: var(--vs-colors--light);
  --vs-state-disabled-controls-color: var(--vs-colors--light);
  --vs-state-disabled-cursor: not-allowed;

  /* Borders */
  --vs-border-color: var(--vs-colors--lightest);
  --vs-border-width: 1px;
  --vs-border-style: solid;
  --vs-border-radius: 4px;

  /* Actions: house the component controls */
  --vs-actions-padding: 4px 6px 0 3px;

  /* Component Controls: Clear, Open Indicator */
  --vs-controls-color: var(--vs-colors--light);
  --vs-controls-size: 1;
  --vs-controls--deselect-text-shadow: 0 1px 0 #fff;

  /* Selected */
  --vs-selected-bg: #f0f0f0;
  --vs-selected-color: var(--vs-colors--dark);
  --vs-selected-border-color: var(--vs-border-color);
  --vs-selected-border-style: var(--vs-border-style);
  --vs-selected-border-width: var(--vs-border-width);

  /* Dropdown */
  --vs-dropdown-bg: #fff;
  --vs-dropdown-color: inherit;
  --vs-dropdown-z-index: 1000;
  --vs-dropdown-min-width: 160px;
  --vs-dropdown-max-height: 350px;
  --vs-dropdown-box-shadow: 0px 3px 6px 0px var(--vs-colors--darkest);

  /* Options */
  --vs-dropdown-option-bg: #000;
  --vs-dropdown-option-color: var(--vs-dropdown-color);
  --vs-dropdown-option-padding: 3px 20px;

  /* Active State */
  --vs-dropdown-option--active-bg: #5897fb;
  --vs-dropdown-option--active-color: #fff;

  /* Deselect State */
  --vs-dropdown-option--deselect-bg: #fb5858;
  --vs-dropdown-option--deselect-color: #fff;

  /* Transitions */
  --vs-transition-timing-function: cubic-bezier(1, -0.115, 0.975, 0.855);
  --vs-transition-duration: 150ms;
}
</style>
