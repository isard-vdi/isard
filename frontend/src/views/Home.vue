<template>
  <b-container fluid>
    <b-row align-h="center" class="pt-4">
      <b-col class="ml-2 mr-2">
        <b-button-group class="float-left">
            <b-button variant="danger" size="lg" @click="logout()">
              <b-icon icon="power" scale="1"></b-icon>
            </b-button>
            <b-button variant="primary" size="lg" v-b-modal.help_modal>
              <b-icon icon="question-circle-fill" scale="1"></b-icon>
            </b-button>
        </b-button-group>
        <Help/>
        <div class="d-flex float-right">
          <label for="switch">
            <b-icon-list></b-icon-list>
          </label>
          <b-form-checkbox id="switch" v-model="gridView" switch class="ml-2 mt-n1"></b-form-checkbox>
          <label for="switch">
            <b-icon-grid></b-icon-grid>
          </label>
        </div>
        <div v-if="!templates_loaded">
          <b-spinner/>
          <p>{{ $t('views.select-template.loading') }}</p>
        </div>

        <div v-else-if="user_templates.length === 0 && user_desktops.length === 0">
          <h1>{{ $t('views.select-template.no-templates.title') }}</h1>
          <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
        </div>

        <div v-else>
          <b-iconstack font-scale="4" class="mb-4 mt-2">
            <b-icon stacked icon="question" variant="primary" shift-v="1.5"></b-icon>
            <b-icon stacked icon="tv" variant="dark" scale="2"></b-icon>
          </b-iconstack>
          <h1 class="mt-4">{{ $t('views.select-template.which-template') }}</h1>
          <div v-if="persistentDesktops.length > 0">
            <h2 class="mt-2">{{ $t('views.select-template.persistent') }}</h2>
            <DesktopsCards :templates="user_templates" :desktops="persistentDesktops"
            :persistent="true" :gridView="gridView" :icons="icons" :status="status"/>
          </div>
          <div v-if="nonpersistentDesktops.length > 0">
            <h2 class="mt-2">{{ $t('views.select-template.volatile') }}</h2>
            <DesktopsCards :templates="user_templates" :desktops="nonpersistentDesktops"
            :persistent="false" :gridView="gridView" :icons="icons" :status="status"/>
          </div>
        </div>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src
import DesktopsCards from '@/components/DesktopsCards.vue'
import Help from '@/components/Help'
import { mapActions } from 'vuex'

export default {
  components: {
    DesktopsCards,
    Help
  },
  created () {
    this.pollData()
    this.$store.dispatch('fetchDesktops')
    this.$store.dispatch('fetchTemplates')
  },
  computed: {
    user () {
      return this.$store.getters.getUser
    },
    user_templates () {
      this.$store.getters.getTemplates.forEach((template) => {
        if (!(template.icon in this.icons)) {
          template.icon = 'default'
        }
      })
      return this.$store.getters.getTemplates
    },
    user_desktops () {
      this.$store.getters.getDesktops.forEach((desktop) => {
        if (!(desktop.icon in this.icons)) {
          desktop.icon = 'default'
        }
      })
      return this.$store.getters.getDesktops
    },
    persistentDesktops () {
      return this.user_desktops.filter(desktop => desktop.type === 'persistent')
    },
    nonpersistentDesktops () {
      return this.user_templates.map(t => this.user_desktops.find((d) => t.id === d.template && d.type === 'nonpersistent') || t)
    },
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    },
    desktops_loaded () {
      return this.$store.getters.getDesktopsLoaded
    }
  },
  mounted: function () {
    if (this.user && this.user.templates && this.user.templates.length === 1) {
      this.$router.push({ name: 'Creating', params: { template: this.user.templates[0].id } })
    }
  },
  data () {
    return {
      polling: null,
      gridView: true,
      icons: {
        default: ['fas', 'desktop'],
        win: ['fab', 'windows'],
        ubuntu: ['fab', 'ubuntu'],
        fedora: ['fab', 'fedora'],
        linux: ['fab', 'linux'],
        centos: ['fab', 'centos']
      },
      status: {
        notCreated: {
          icon: ['fas', 'play'],
          variant: 'success'
        },
        started: {
          action: 'stop',
          icon: ['fas', 'stop'],
          variant: 'danger'
        },
        stopped: {
          action: 'start',
          icon: ['fas', 'play'],
          variant: 'success'
        }
      }
    }
  },
  methods: {
    ...mapActions([
      'logout'
    ]),
    pollData () {
      this.polling = setInterval(() => {
        this.$store.dispatch('fetchDesktops')
        this.$store.dispatch('fetchTemplates')
      }, 15000)
    }
  }
}
</script>
