<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
      <StatusBar/>
    </div>
    <b-container fluid id="content">
      <div v-if="(getDesktopsLoaded && getTemplatesLoaded) && (getTemplates.length === 0 && getDesktops.length === 0)">
            <h3><strong>{{ $t('views.select-template.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
      </div>
      <b-tabs v-else>
        <b-tab v-if="!(getDesktopsLoaded && getTemplatesLoaded) || persistentDesktops.length > 0" active>
          <template #title>
            <b-spinner v-if="!(getDesktopsLoaded && getTemplatesLoaded)" type="border" small></b-spinner>
            <span class="d-inline d-xl-none">{{ $t('views.select-template.persistent-compact') }}</span><span class="ml-2 d-none d-xl-inline">{{ $t('views.select-template.persistent') }}</span>
          </template>
          <template v-if="getViewType === 'grid'">
                <card-list
                  :templates="getTemplates"
                  :desktops="persistentDesktops"
                  :persistent="true"
                  :loading="!(getDesktopsLoaded && getTemplatesLoaded)">
                </card-list>
            </template>
            <template v-else>
              <TableList
                  :templates="getTemplates"
                  :desktops="persistentDesktops"
                  :persistent="true"
                  :loading="!(getDesktopsLoaded && getTemplatesLoaded)"></TableList>
            </template>
        </b-tab>

        <b-tab v-if="!(getDesktopsLoaded && getTemplatesLoaded)  || visibleNonPersistentDesktops.length > 0">
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
  </div>
</template>

<script>
// @ is an alias to /src
import { mapGetters } from 'vuex'
import NewNavBar from '@/components/NewNavBar.vue'
import StatusBar from '@/components/StatusBar.vue'
import CardList from '@/components/CardList.vue'
import TableList from '@/components/TableList.vue'

export default {
  components: {
    StatusBar,
    NewNavBar,
    CardList,
    TableList
  },
  created () {
    this.$store.dispatch('fetchDesktops')
    this.$store.dispatch('fetchTemplates')
  },
  computed: {
    ...mapGetters([
      'getTemplates',
      'getDesktops',
      'getTemplatesLoaded',
      'getDesktopsLoaded',
      'getViewType',
      'getShowStarted'
    ]),
    persistentDesktops () {
      return this.getDesktops.filter(desktop => this.getShowStarted ? desktop.type === 'persistent' && desktop.state === 'Started' : desktop.type === 'persistent')
    },
    nonpersistentDesktops () {
      return this.getTemplates.map(template => this.getDesktops.find((desktop) => template.id === desktop.template && desktop.type === 'nonpersistent') || template)
    },
    visibleNonPersistentDesktops () {
      return this.nonpersistentDesktops.filter(desktop => this.getShowStarted ? desktop.state : desktop.name)
    }
  },
  data () {
    return {
      gridView: true
    }
  },
  mounted () {
    console.log('Home mounted')
    this.$store.dispatch('openSocket', { room: 'desktops' })
  },
  destroyed () {
    this.$store.dispatch('closeSocket')
  }
}
</script>
