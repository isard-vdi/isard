<template>
  <b-container fluid id="content">
      <div v-if="getDesktopsLoaded && getTemplatesLoaded && getTemplates.length === 0 && getDesktops.length === 0">
            <h3><strong>{{ $t('views.select-template.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
      </div>
      <div v-else-if="getDesktopsLoaded && getTemplatesLoaded && visibleNonPersistentDesktops.length === 0 && filteredPersistentDesktops.length === 0">
            <h3><strong>{{ $t('views.select-template.no-desktops-filtered.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-desktops-filtered.subtitle') }}</p>
      </div>
      <b-tabs v-else>
        <b-tab v-if="(getDesktopsLoaded && getTemplatesLoaded) || filteredPersistentDesktops.length > 0"
          :active="currentTab === 'desktops'"
          @click="updateCurrentTab('desktops')">
          <template #title>
            <b-spinner v-if="!(getDesktopsLoaded && getTemplatesLoaded)" type="border" small></b-spinner>
            <span class="d-inline d-xl-none">{{ $t('views.select-template.persistent-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.select-template.persistent') }}</span>
          </template>
          <template v-if="getDesktops.length === 0">
            <div class="m-4">
              <h3><strong>{{ $t('views.select-template.no-desktops.title') }}</strong></h3>
              <p>{{ $t('views.select-template.no-desktops.subtitle') }}</p>
            </div>
          </template>
          <template v-else-if="getViewType === 'grid'">
                <card-list
                  :templates="getTemplates"
                  :desktops="filteredPersistentDesktops"
                  :persistent="true"
                  :loading="!(getDesktopsLoaded && getTemplatesLoaded)">
                </card-list>
            </template>
            <template v-else>
              <TableList
                  :templates="getTemplates"
                  :desktops="filteredPersistentDesktops"
                  :persistent="true"
                  :loading="!(getDesktopsLoaded && getTemplatesLoaded)"></TableList>
            </template>
        </b-tab>

        <b-tab v-if="!(getDesktopsLoaded && getTemplatesLoaded)  || visibleNonPersistentDesktops.length > 0"
          :active="currentTab === 'templates'"
          @click="updateCurrentTab('templates')">
          <template #title>
            <b-spinner v-if="!(getDesktopsLoaded && getTemplatesLoaded)" type="border" small></b-spinner>
            <span class="d-inline d-xl-none">{{ $t('views.select-template.volatile-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.select-template.volatile') }}</span>
          </template>
              <template v-if="getViewType === 'grid'">
                <CardList
                    :templates="getTemplates"
                    :desktops="visibleNonPersistentDesktops"
                    :persistent="false"
                    :loading="!(getDesktopsLoaded && getTemplatesLoaded)">
                </CardList>
            </template>
            <template v-else>
               <TableList
                    :templates="getTemplates"
                    :desktops="visibleNonPersistentDesktops"
                    :persistent="false"
                    :loading="!(getDesktopsLoaded && getTemplatesLoaded)">
                </TableList>
            </template>
        </b-tab>
      </b-tabs>
    </b-container>
</template>

<script>
// @ is an alias to /src
import { mapGetters, mapActions } from 'vuex'
import CardList from '@/components/CardList.vue'
import TableList from '@/components/TableList.vue'
import { computed } from '@vue/composition-api'
import { desktopStates } from '@/shared/constants'

export default {
  components: {
    CardList,
    TableList
  },
  setup (_, context) {
    const $store = context.root.$store

    $store.dispatch('fetchDesktops')
    $store.dispatch('fetchAllowedTemplates')

    const currentTab = computed(() => $store.getters.getCurrentTab)
    const showStarted = computed(() => $store.getters.getShowStarted)
    const desktops = computed(() => $store.getters.getDesktops)
    const templates = computed(() => $store.getters.getTemplates)
    const filterDesktopsText = computed(() => $store.getters.getDesktopsFilter)

    const persistentDesktops = computed(() => desktops.value.filter(desktop => showStarted.value ? desktop.type === 'persistent' && [desktopStates.started, desktopStates.waitingip].includes(desktop.state.toLowerCase()) : desktop.type === 'persistent'))
    const nonpersistentDesktops = computed(() => templates.value.map(template => desktops.value.find((desktop) => template.id === desktop.template && desktop.type === 'nonpersistent') || template))

    const filteredPersistentDesktops = computed(() => persistentDesktops.value.filter(desktop => desktop.name.toLowerCase().includes(filterDesktopsText.value.toLowerCase())))
    const filteredNonPersistentDesktops = computed(() => nonpersistentDesktops.value.filter(desktop => desktop.name.toLowerCase().includes(filterDesktopsText.value.toLowerCase())))

    const visibleNonPersistentDesktops = computed(() => filteredNonPersistentDesktops.value.filter(desktop => showStarted.value ? desktop.state && desktop.state.toLowerCase() === 'started' : desktop.name))

    return {
      filteredPersistentDesktops,
      visibleNonPersistentDesktops,
      currentTab
    }
  },
  methods: {
    ...mapActions([
      'updateCurrentTab'
    ])
  },
  computed: {
    ...mapGetters([
      'getTemplates',
      'getDesktops',
      'getTemplatesLoaded',
      'getDesktopsLoaded',
      'getViewType'
    ])
  }
}
</script>
