<template>
  <div>
    <div class="header-wrapper">
      <NewNavBar/>
      <StatusBar/>
    </div>
    <b-container fluid id="content">
          <div v-if="!templates_loaded">
            <b-spinner/>
            <p>{{ $t('views.select-template.loading') }}</p>
          </div>

          <div v-else-if="user_templates.length === 0 && user_desktops.length === 0">
            <h1>{{ $t('views.select-template.no-templates.title') }}</h1>
            <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
          </div>

          <div v-else>
            <template v-if="viewType === 'grid'">
              <div v-if="persistentDesktops.length > 0">
                <card-list
                  :listTitle="$t('views.select-template.persistent')"
                  :templates="user_templates"
                  :desktops="persistentDesktops"
                  :persistent="true">
                </card-list>
              </div>
              <div v-if="nonpersistentDesktops.length > 0">
                <card-list
                    :listTitle="$t('views.select-template.volatile')"
                    :templates="user_templates"
                    :desktops="visibleNonPersistentDesktops"
                    :persistent="false">
                </card-list>
              </div>
            </template>
            <template v-else>

            </template>
          </div>
    </b-container>
  </div>
</template>

<script>
// @ is an alias to /src
import NewNavBar from '@/components/NewNavBar.vue'
import StatusBar from '@/components/StatusBar.vue'
import CardList from '@/components/CardList.vue'

export default {
  components: {
    StatusBar,
    NewNavBar,
    CardList
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
