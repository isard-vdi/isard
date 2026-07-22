<template>
  <b-modal
    id="allowedModal"
    v-model="showIncreaseModal"
    size="lg"
    :title="$t(`forms.increase.modal.title`)"
    centered
    @hidden="closeIncreaseModal"
  >
    <div class="mx-4 mb-2">
      <b-row>
        <b-col
          cols="6"
        >
          <label for="currentSize">
            {{ $t('forms.increase.current-size') }}
          </label>
          <b-input-group
            append="GB"
          >
            <b-form-input
              id="currentSize"
              v-model="currentSize"
              type="number"
              disabled
            />
          </b-input-group>
        </b-col>
        <b-col
          cols="6"
        >
          <label for="newSize">
            {{ $t('forms.increase.new-size') }}
          </label>
          <b-input-group
            append="GB"
          >
            <b-form-input
              id="newSize"
              v-model="newSize"
              type="number"
              :state="increaseValidate"
            />
          </b-input-group>
          <b-form-invalid-feedback
            :state="increaseValidate"
          >
            {{ $t('forms.increase.errors.too-small') }}
          </b-form-invalid-feedback>
        </b-col>
      </b-row>
    </div>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          squared
          variant="primary"
          class="float-right"
          @click="updateIncrease"
        >
          {{ $t(`forms.increase.modal.buttons.update`) }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref, watch } from '@vue/composition-api'
import { mapGetters } from 'vuex'
import i18n from '@/i18n'

export default {
  components: { },
  setup (_, context) {
    const $store = context.root.$store

    const item = computed(() => $store.getters.getIncreaseItem)

    const currentSize = ref(0)
    watch(item, (newVal) => {
      currentSize.value = (newVal.virtualSize / 1024 / 1024 / 1024).toFixed(0)
    })

    const newSize = ref(currentSize.value)
    watch(currentSize, (newVal) => {
      newSize.value = parseInt(newVal) + 1
    })

    const priorityOptions = [
      { value: 'low', text: i18n.t('forms.increase.priority-options.low') },
      { value: 'medium', text: i18n.t('forms.increase.priority-options.medium') },
      { value: 'high', text: i18n.t('forms.increase.priority-options.high') }
    ]
    const priority = ref('low')

    const showIncreaseModal = computed({
      get: () => $store.getters.getShowIncreaseModal,
      set: (value) => $store.commit('setShowIncreaseModal', value)
    })

    const increaseValidate = computed(() => {
      return !(parseInt(newSize.value) <= parseInt(currentSize.value))
    })

    const updateIncrease = () => {
      if (parseInt(newSize.value) > parseInt(currentSize.value)) {
        const increment = parseInt(newSize.value) - parseInt(currentSize.value)
        $store.dispatch('updateIncrease', { id: item.value.id, increment: increment, priority: priority.value })
        closeIncreaseModal()
      }
    }

    const closeIncreaseModal = () => {
      priority.value = 'low'
      $store.dispatch('showIncreaseModal', { item: {}, show: false })
    }

    return {
      item,
      currentSize,
      newSize,
      priorityOptions,
      priority,
      showIncreaseModal,
      increaseValidate,
      updateIncrease,
      closeIncreaseModal
    }
  },
  computed: {
    ...mapGetters([
      'getUser'
    ])
  }
}
</script>
