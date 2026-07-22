<template>
  <button
    v-if="visible"
    type="button"
    class="frontend-toggler"
    :disabled="!hasEquivalent"
    :title="hasEquivalent ? $t('frontend_toggler.to_vue3') : $t('frontend_toggler.no_equivalent')"
    @click="switchFrontend"
  >
    {{ hasEquivalent ? $t('frontend_toggler.to_vue3') : $t('frontend_toggler.no_equivalent') }}
  </button>
</template>

<script>
import { mapGetters } from 'vuex'
import { EDIT_FORM_ROUTES, VUE2_TO_VUE3, resolveVue3Path } from '@/shared/frontendModeMap'

export default {
  name: 'FrontendToggler',
  computed: {
    ...mapGetters(['getConfig']),
    visible () {
      if (this.getConfig.frontendMode !== 'all') return false
      const name = this.$route && this.$route.name
      if (!name) return false
      return !EDIT_FORM_ROUTES.has(name)
    },
    hasEquivalent () {
      const name = this.$route && this.$route.name
      return Boolean(name && VUE2_TO_VUE3[name])
    }
  },
  methods: {
    switchFrontend () {
      const target = resolveVue3Path(this.$route)
      if (target) {
        window.location.assign(target)
      }
    }
  }
}
</script>

<style scoped>
.frontend-toggler {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 1050;
  padding: 8px 16px;
  border-radius: 999px;
  border: none;
  font-size: 0.875rem;
  font-weight: 600;
  color: #ffffff;
  background-color: #0d6efd;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  cursor: pointer;
}

.frontend-toggler:hover:not(:disabled) {
  background-color: #0b5ed7;
}

.frontend-toggler:disabled {
  background-color: #9aa0a6;
  cursor: not-allowed;
}
</style>
