<template>
  <b-container
    id="content"
    fluid
  >
    <b-tabs>
      <b-tab
        :active="currentTab === 'templates'"
        @click="updateCurrentTab('templates')"
      >
        <template #title>
          <b-spinner
            v-if="!(getTemplatesLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.templates.tabs.templates-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.templates.tabs.templates') }}</span>
        </template>
        <template v-if="getTemplatesLoaded && getTemplates.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.templates.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.templates.no-templates.subtitle') }}</p>
          </div>
        </template>
        <template v-else>
          <TemplatesList
            :templates="getTemplates"
            :loading="!(getTemplatesLoaded)"
          />
        </template>
      </b-tab>
      <b-tab
        :active="currentTab === 'sharedTemplates'"
        @click="updateCurrentTab('sharedTemplates')"
      >
        <template #title>
          <b-spinner
            v-if="!(getSharedTemplatesLoaded)"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.templates.tabs.shared-templates-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.templates.tabs.shared-templates') }}</span>
        </template>
        <template v-if="getSharedTemplatesLoaded && getSharedTemplates.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.templates.no-shared-templates.title') }}</strong></h3>
            <p>{{ $t('views.templates.no-shared-templates.subtitle') }}</p>
          </div>
        </template>
        <template v-else>
          <TemplatesList
            :shared="true"
            :templates="getSharedTemplates"
            :loading="!(getSharedTemplatesLoaded)"
          />
        </template>
      </b-tab>
    </b-tabs>
    <AllowedModal @updateAllowed="updateAllowed" />
    <DeleteTemplateModal />
  </b-container>
</template>
<script>
// @ is an alias to /src
import TemplatesList from '@/components/templates/TemplatesList.vue'
import AllowedModal from '@/components/AllowedModal.vue'
import DeleteTemplateModal from '@/components/templates/DeleteTemplateModal.vue'
import { mapGetters } from 'vuex'
import { computed } from '@vue/composition-api'

export default {
  components: {
    TemplatesList, AllowedModal, DeleteTemplateModal
  },
  setup (props, context) {
    const $store = context.root.$store
    $store.dispatch('fetchTemplates')
    $store.dispatch('fetchAllowedTemplates', 'shared')

    const templateId = computed(() => $store.getters.getId)

    const updateAllowed = (allowed) => {
      $store.dispatch('updateAllowed', { table: 'domains', id: templateId.value, allowed: allowed })
    }

    const currentTab = computed(() => $store.getters.getCurrentTab)

    const updateCurrentTab = (currentTab) => {
      $store.dispatch('updateCurrentTab', currentTab)
    }

    return {
      updateAllowed,
      currentTab,
      updateCurrentTab
    }
  },
  computed: {
    ...mapGetters([
      'getTemplates',
      'getTemplatesLoaded',
      'getSharedTemplates',
      'getSharedTemplatesLoaded'
    ]),
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    }
  },
  destroyed () {
    this.$store.dispatch('resetTemplatesState')
  }
}
</script>
