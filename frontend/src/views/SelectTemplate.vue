<template>
  <b-container fluid class="vh-100">
    <b-row class="h-100 d-flex justify-content-center align-items-center mt-4">
      <b-col md="1"/>
      <b-col md="10" class="mt-4">
        <div v-if="!templates_loaded">
          <b-spinner/>
          <p>{{ $t('views.select-template.loading') }}</p>
        </div>

        <div v-else-if="user_templates.length === 0">
          <h1>{{ $t('views.select-template.no-templates.title') }}</h1>
          <p>{{ $t('views.select-template.no-templates.subtitle') }}</p>
        </div>

        <div v-else>
          <b-iconstack font-scale="6" class="mb-4">
            <b-icon stacked icon="question" variant="primary" shift-v="1.5"></b-icon>
            <b-icon stacked icon="tv" variant="dark" scale="2"></b-icon>
          </b-iconstack>
          <h1 class="mt-4">{{ $t('views.select-template.which-template') }}</h1>
          <b-container fluid class="mb-4">
              <transition-group appear name="bounce" tag="b-row">
                <b-col class="big_button mt-2 mr-2 ml-2" v-for="template in user_templates"
                :key="template.name" @click="chooseDesktop(template.id)">
                  <font-awesome-icon size="6x" :icon="icons[template.icon]" />
                  <p class="mt-4">{{ template.name }}</p>
                </b-col>
              </transition-group>
          </b-container>
        </div>
      </b-col>
      <b-col md="1"/>
    </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  created () {
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
    templates_loaded () {
      return this.$store.getters.getTemplatesLoaded
    }
  },
  methods: {
    chooseDesktop (template) {
      this.$router.push({ name: 'Creating', params: { template: template } })
    }
  },
  mounted: function () {
    if (this.user && this.user.templates && this.user.templates.length === 1) {
      this.$router.push({ name: 'Creating', params: { template: this.user.templates[0].id } })
    }
  },
  data () {
    return {
      icons: {
        default: ['fas', 'desktop'],
        win: ['fab', 'windows'],
        ubuntu: ['fab', 'ubuntu'],
        fedora: ['fab', 'fedora'],
        linux: ['fab', 'linux'],
        centos: ['fab', 'centos']
      }
    }
  }
}
</script>

<style scoped>
  .big_button {
    background-color:white;
    border: 5px solid #e9ecef;
    border-radius: 2rem;
    min-height:250px !important;
    min-width:250px !important;
    padding-top: 50px;
    padding-bottom: 25px;
  }

  .big_button:hover {
    background-color: #e9ecef;
    cursor: pointer;
  }

  .bounce-enter-active {
    animation: bounce-in .5s;
  }
  .bounce-leave-active {
    animation: bounce-in .5s reverse;
  }
  @keyframes bounce-in {
    0% {
      transform: scale(0);
    }
    50% {
      transform: scale(1.5);
    }
    100% {
      transform: scale(1);
    }
  }
</style>
