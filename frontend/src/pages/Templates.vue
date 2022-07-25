<template>
  <b-container
    id="content"
    fluid
  >
    <div v-if="templates_loaded && getTemplates.length === 0">
      <h3><strong>{{ $t('views.templates.no-templates.title') }}</strong></h3>
      <p>{{ $t('views.templates.no-templates.subtitle') }}</p>
    </div>
    <TemplatesList
      v-else
      :templates="getTemplates"
      :loading="!(templates_loaded)"
    />
    <AllowedModal @updateAllowed="updateAllowed" />
  </b-container>
</template>
<script>
// @ is an alias to /src
import TemplatesList from '@/components/templates/TemplatesList.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import { mapGetters } from 'vuex'
import { computed } from '@vue/composition-api'

export default {
  components: {
    TemplatesList, AllowedModal
  },
  setup (props, context) {
    const $store = context.root.$store
    const templateId = computed(() => $store.getters.getId)

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'domains', id: templateId.value, allowed: allowed })
    }

    return {
      updateAllowed
    }
  },
  computed: {
    ...mapGetters(['getTemplates']),
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    }
  },
  created () {
    this.$store.dispatch('fetchTemplates')
  },
  destroyed () {
    this.$store.dispatch('resetTemplatesState')
  }
}
</script>
