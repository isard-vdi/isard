<template>
  <form>
    <b-modal
      id="spice_help_modal"
      ref="spice_help_modal"
      size="lg"
      content-class="shadow"
      centered
      :ok-title="$t('views.direct-viewer.help.spice.close-guide')"
      ok-only
      hide-header
    >
      <b-container class="text-left">
        <h3>
          <b-icon
            icon="star-fill"
            variant="warning"
          />
          {{ $t('views.direct-viewer.help.spice.local-client') }}
        </h3>
        <hr>
        <b>{{ $t('views.direct-viewer.help.spice.best-performance') }}</b>
        {{ $t('views.direct-viewer.help.spice.spice-client-required') }} <br>
        {{ $t('views.direct-viewer.help.spice.generic-text') }}
        <b-row class="justify-content-md-center">
          <b-button
            variant="outline-primary"
            class="my-4"
            :href="$t('views.direct-viewer.help.spice.download-link')"
          >
            {{ $t('views.direct-viewer.help.spice.download-install') }}
          </b-button>
        </b-row>
        <div
          v-if="os!='MacOS'"
          class="mb-4"
        >
          {{ $t('views.direct-viewer.help.spice.once-installed') }}
        </div>
      </b-container>
    </b-modal>
  </form>
</template>

<script>
// @ is an alias to /src

export default {
  data () {
    return {
      os: this.getOS()
    }
  },
  methods: {
    getOS () {
      const userAgent = window.navigator.userAgent
      const platform = window.navigator.platform
      const macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K', 'Mac OS']
      const windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE']
      const iosPlatforms = ['iPhone', 'iPad', 'iPod']
      let os = null

      if (macosPlatforms.indexOf(platform) !== -1) {
        os = 'MacOS'
      } else if (iosPlatforms.indexOf(platform) !== -1) {
        os = 'iOS'
      } else if (windowsPlatforms.indexOf(platform) !== -1) {
        os = 'Windows'
      } else if (/Android/.test(userAgent)) {
        os = 'Android'
      } else if (!os && /Linux/.test(platform)) {
        os = 'Linux'
      }
      return os
    }
  }
}
</script>

<style scoped>
ul {
    margin-top: 15px;
}
li {
    margin-top: 10px;
    margin-right: 75px;
    cursor: auto !important;
    display: flex;
    justify-content: space-between;
}

b {
    cursor: auto !important;
}

code {
    cursor: auto !important;
}

a b {
    cursor: pointer !important;
}
</style>
