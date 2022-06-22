<template>
  <b-container fluid id="content">
    <div v-if="templates_loaded && getTemplates.length === 0">
      <h3><strong>{{ $t('views.templates.no-templates.title') }}</strong></h3>
      <p>{{ $t('views.templates.no-templates.subtitle') }}</p>
    </div>
    <TemplatesList v-else
      :templates="getTemplates"
      :loading="!(templates_loaded)"/>
  </b-container>
</template>
<script>
// @ is an alias to /src
import TemplatesList from '@/components/templates/TemplatesList.vue'
import { mapGetters } from 'vuex'

export default {
  components: {
    TemplatesList
  },
  created () {
    this.$store.dispatch('fetchTemplates')
  },
  computed: {
    ...mapGetters(['getTemplates']),
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    }
  },
  mounted () {
    this.$store.dispatch('openSocket', { room: 'templates' })
  },
  destroyed () {
    this.$store.dispatch('closeSocket')
    this.$store.dispatch('resetTemplatesState')
  }
}
</script>
