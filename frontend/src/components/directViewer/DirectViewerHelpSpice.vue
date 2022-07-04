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
        {{ $t('views.direct-viewer.help.spice.spice-client-required') }}
        <div v-if="os=='Windows' || os==null">
          {{ $t('views.direct-viewer.help.spice.text.windows') }}
          <ul @click.stop>
            <li>
              <b>Windows 64bits (Windows 10):</b>
              <b-button
                variant="outline-primary"
                href="https://virt-manager.org/download/sources/virt-viewer/virt-viewer-x64-7.0.msi"
              >
                {{ $t('views.direct-viewer.help.spice.install') }}
              </b-button>
            </li>
            <li>
              <b>Windows 32bits ({{ $t('views.direct-viewer.help.spice.other-windows-versions') }}):</b>
              <b-button
                variant="outline-primary"
                href="https://virt-manager.org/download/sources/virt-viewer/virt-viewer-x86-7.0.msi"
              >
                {{ $t('views.direct-viewer.help.spice.install') }}
              </b-button>
            </li>
          </ul>
        </div>
        <div v-if="os=='Linux' || os==null">
          {{ $t('views.direct-viewer.help.spice.text.linux') }}
          <ul @click.stop>
            <li>
              <b>Debian / Ubuntu:</b>
              <code>sudo apt install virt-viewer -y</code>
            </li>
            <li>
              <b>RedHat / CentOS / Fedora:</b>
              <code>sudo dnf install remote-viewer -y</code>
            </li>
          </ul>
        </div>
        <div v-if="os=='Android' || os==null">
          {{ $t('views.direct-viewer.help.spice.text.android') }}
          <ul @click.stop>
            <li>
              <b>Android:</b>
              <b-button
                variant="outline-primary"
                href="https://play.google.com/store/apps/details?id=com.iiordanov.freeaSPICE"
              >
                {{ $t('views.direct-viewer.help.spice.install') }}
              </b-button>
            </li>
          </ul>
        </div>
        <div v-if="os=='iOS' || os==null">
          {{ $t('views.direct-viewer.help.spice.text.ios') }}
          <ul @click.stop>
            <li>
              <b>iOS:</b>
              <b-button
                variant="outline-primary"
                href="https://itunes.apple.com/us/app/flexvdi-client/id1051361263"
              >
                {{ $t('views.direct-viewer.help.spice.install') }}
              </b-button>
            </li>
          </ul>
        </div>
        <div v-if="os=='MacOS' || os==null">
          {{ $t('views.direct-viewer.help.spice.text.macos') }}
        </div>
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
