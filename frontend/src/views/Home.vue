<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
      <StatusBar/>
    </div>
    <b-container fluid id="content">
      <div v-if="(desktops_loaded && templates_loaded) && (user_templates.length === 0 && user_desktops.length === 0)">
            <h3><strong>{{ $t('views.select-template.no-templates.title') }}</strong></h3>
            <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
      </div>
      <b-tabs v-else>
        <b-tab v-if="!(desktops_loaded && templates_loaded) || persistentDesktops.length > 0" active>
          <template #title>
            <b-spinner v-if="!(desktops_loaded && templates_loaded)" type="border" small></b-spinner>
            {{ $t('views.select-template.persistent') }}
          </template>
          <template v-if="viewType === 'grid'">
                <card-list
                  :templates="user_templates"
                  :desktops="persistentDesktops"
                  :persistent="true"
                  :loading="!(desktops_loaded && templates_loaded)">
                </card-list>
            </template>
            <template v-else>
              <TableList
                  :templates="user_templates"
                  :desktops="persistentDesktops"
                  :persistent="true"
                  :loading="!(desktops_loaded && templates_loaded)"></TableList>
            </template>
        </b-tab>

        <b-tab v-if="!(desktops_loaded && templates_loaded)  || visibleNonPersistentDesktops.length > 0">
          <template #title>
            <b-spinner v-if="!(desktops_loaded && templates_loaded)" type="border" small></b-spinner> {{$t('views.select-template.volatile')}}
          </template>
              <template v-if="viewType === 'grid'">
                <card-list
                    :templates="user_templates"
                    :desktops="visibleNonPersistentDesktops"
                    :persistent="false"
                    :loading="!(desktops_loaded && templates_loaded)">
                </card-list>
            </template>
            <template v-else>
               <TableList
                    :templates="user_templates"
                    :desktops="visibleNonPersistentDesktops"
                    :persistent="false"
                    :loading="!(desktops_loaded && templates_loaded)"></TableList>
            </template>
        </b-tab>
      </b-tabs>
    </b-container>
  </div>
</template>

<script>
// @ is an alias to /src
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
    user () {
      return this.$store.getters.getUser
    },
    user_templates () {
      return this.$store.getters.getTemplates
    },
    user_desktops () {
      return this.$store.getters.getDesktops
    },
    persistentDesktops () {
      return this.$store.getters.getDesktops.filter(desktop => this.getShowStarted ? desktop.type === 'persistent' && desktop.state === 'Started' : desktop.type === 'persistent')
    },
    nonpersistentDesktops () {
      return this.$store.getters.getTemplates.map(template => this.$store.getters.getDesktops.find((desktop) => template.id === desktop.template && desktop.type === 'nonpersistent') || template)
    },
    visibleNonPersistentDesktops () {
      return this.nonpersistentDesktops.filter(desktop => this.getShowStarted ? desktop.state : desktop.name)
    },
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    },
    desktops_loaded () {
      return this.$store.getters.getDesktopsLoaded
    },
    viewType () {
      return this.$store.getters.getViewType
    },
    getShowStarted () {
      return this.$store.getters.getShowStarted
    }
  },
  data () {
    return {
      polling: null,
      gridView: true
    }
  }
}
</script>
