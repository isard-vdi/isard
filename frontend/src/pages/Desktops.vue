<template>
  <b-container
    id="content"
    fluid
  >
    <b-tabs>
      <b-tab
        v-if="hasDesktopQuota"
        :active="currentTab === 'desktops'"
        @click="updateCurrentTab('desktops')"
      >
        <DirectLinkModal />
        <StartNowModal />
        <CantStartNowModal />
        <DesktopModal />
        <template #title>
          <b-spinner
            v-if="!getDesktopsLoaded"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.select-template.persistent-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.select-template.persistent') }}</span>
        </template>
        <template v-if="getDesktopsLoaded && getDesktops.length === 0">
          <div class="m-4">
            <h3><strong>{{ $t('views.select-template.no-desktops.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-desktops.subtitle') }}</p>
          </div>
        </template>
        <div
          v-else-if="getDesktopsLoaded && getDesktops.length > 0 && filteredPersistentDesktops.length === 0"
          class="mt-4 ml-4"
        >
          <h3><strong>{{ $t('views.select-template.no-desktops-filtered.title') }}</strong></h3>
          <p>{{ $t('views.select-template.no-desktops-filtered.subtitle') }}</p>
        </div>
        <template v-else-if="getViewType === 'grid'">
          <card-list
            :templates="getTemplates"
            :desktops="filteredPersistentDesktops"
            :persistent="true"
            :loading="!getDesktopsLoaded"
          />
        </template>
        <template v-else>
          <TableList
            :templates="getTemplates"
            :desktops="filteredPersistentDesktops"
            :persistent="true"
            :loading="!getDesktopsLoaded"
          />
        </template>
      </b-tab>

      <b-tab
        v-if="config.showTemporalTab && hasTemporalQuota"
        :active="currentTab === 'templates'"
        @click="updateCurrentTab('templates')"
      >
        <template #title>
          <b-spinner
            v-if="!getTemplatesLoaded"
            type="border"
            small
          />
          <span class="d-inline d-xl-none">{{ $t('views.select-template.volatile-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.select-template.volatile') }}</span>
        </template>
        <template v-if="getTemplatesLoaded && getTemplates.length === 0">
          <div class="mt-4 ml-4">
            <h3><strong>{{ $t('views.select-template.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
          </div>
        </template>
        <div
          v-else-if="getTemplatesLoaded && getTemplates.length > 0 && visibleNonPersistentDesktops.length === 0"
          class="mt-4 ml-4"
        >
          <h3><strong>{{ $t('views.select-template.no-templates-filtered.title') }}</strong></h3>
        </div>
        <template v-else-if="getViewType === 'grid'">
          <CardList
            :templates="getTemplates"
            :desktops="visibleNonPersistentDesktops"
            :persistent="false"
            :loading="!getTemplatesLoaded"
          />
        </template>
        <template v-else>
          <TableList
            :templates="getTemplates"
            :desktops="visibleNonPersistentDesktops"
            :persistent="false"
            :loading="!getTemplatesLoaded"
          />
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
import { computed, watch } from '@vue/composition-api'
import { desktopStates } from '@/shared/constants'
import DirectLinkModal from '../components/directViewer/DirectLinkModal.vue'
import StartNowModal from '@/components/booking/StartNowModal.vue'
import CantStartNowModal from '@/components/booking/CantStartNowModal.vue'
import DesktopModal from '@/components/desktops/DesktopModal.vue'

export default {
  components: {
    CardList,
    TableList,
    DirectLinkModal,
    StartNowModal,
    CantStartNowModal,
    DesktopModal
  },
  setup (_, context) {
    const $store = context.root.$store
    const config = computed(() => $store.getters.getConfig)

    watch(config, (newVal, prevVal) => {
      if (newVal.showTemporalTab) {
        $store.dispatch('fetchAllowedTemplates', 'all')
      } else {
        $store.dispatch('setTemplatesLoaded', true)
      }
    }, { immediate: true })

    $store.dispatch('fetchDesktops')
    $store.dispatch('fetchProfile')

    const currentTab = computed(() => $store.getters.getCurrentTab)
    const showStarted = computed(() => $store.getters.getShowStarted)
    const desktops = computed(() => $store.getters.getDesktops)
    const templates = computed(() => $store.getters.getTemplates)
    const filterDesktopsText = computed(() => $store.getters.getDesktopsFilter)

    const hasDesktopQuota = computed(() => $store.getters.getProfile.quota === false || $store.getters.getProfile.quota.desktops)
    const hasTemporalQuota = computed(() => $store.getters.getProfile.quota === false || $store.getters.getProfile.quota.volatile)

    const persistentDesktops = computed(() => desktops.value.filter(desktop => showStarted.value ? desktop.type === 'persistent' && [desktopStates.started, desktopStates.waitingip, desktopStates['shutting-down']].includes(desktop.state.toLowerCase()) : desktop.type === 'persistent'))
    const nonpersistentDesktops = computed(() => templates.value.map(template => desktops.value.find((desktop) => template.id === desktop.template && desktop.type === 'nonpersistent') || template))

    const filteredPersistentDesktops = computed(() => persistentDesktops.value.filter(desktop => desktop.name.toLowerCase().includes(filterDesktopsText.value.toLowerCase())))
    const filteredNonPersistentDesktops = computed(() => nonpersistentDesktops.value.filter(desktop => desktop.name.toLowerCase().includes(filterDesktopsText.value.toLowerCase())))

    const visibleNonPersistentDesktops = computed(() => filteredNonPersistentDesktops.value.filter(desktop => showStarted.value ? desktop.state && desktop.state.toLowerCase() === 'started' : desktop.name))

    return {
      filteredPersistentDesktops,
      visibleNonPersistentDesktops,
      currentTab,
      config,
      hasDesktopQuota,
      hasTemporalQuota
    }
  },
  computed: {
    ...mapGetters([
      'getTemplates',
      'getDesktops',
      'getTemplatesLoaded',
      'getDesktopsLoaded',
      'getViewType'
    ])
  },
  destroyed () {
    this.$store.dispatch('resetDesktopsState')
    this.$store.dispatch('resetTemplatesState')
  },
  methods: {
    ...mapActions([
      'updateCurrentTab'
    ])
  }

}
</script>
