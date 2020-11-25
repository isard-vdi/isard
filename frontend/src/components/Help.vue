<template>
    <form>
        <b-modal
            id="help_modal"
            size="lg"
            content-class="shadow"
            centered
            ref="help_modal"
            :ok-title="$t('components.help.close-guide')"
            ok-only
            hide-header
        >
            <b-container class="text-left">
                <h3>
                    <b-icon icon="star-fill" variant="warning"></b-icon>
                    {{ $t('components.help.local-client') }}
                </h3>
                <hr />
                <b>{{ $t('components.help.best-performance') }}</b>
                {{ this.text }}
                <ul v-on:click.stop>
                    <div v-if="os=='Windows'">
                        <ul>
                            <li>
                                <b>Windows 64bits (Windows 10):</b>
                                <a
                                    href="https://virt-manager.org/download/sources/virt-viewer/virt-viewer-x64-7.0.msi"
                                    style="text-align: right"
                                >
                                    <b>{{ $t('components.help.install') }}</b>
                                </a>
                            </li>
                            <li>
                                <b>Windows 32bits ({{ $t('components.help.other-window-versions') }}):</b>
                                <a
                                    href="https://virt-manager.org/download/sources/virt-viewer/virt-viewer-x86-7.0.msi"
                                >
                                    <b>{{ $t('components.help.install') }}</b>
                                </a>
                            </li>
                        </ul>
                    </div>
                    <div v-else-if="os=='Linux'">
                        <li>
                            <b>Debian / Ubuntu:</b>
                            <code>sudo apt install virt-viewer -y</code>
                        </li>
                        <li>
                            <b>RedHat / CentOS / Fedora:</b>
                            <code>sudo dnf install remote-viewer -y</code>
                        </li>
                    </div>
                    <div v-else-if="os=='Android'">
                        <li>
                            <b>Android:</b>
                            <a
                                href="https://play.google.com/store/apps/details?id=com.iiordanov.freeaSPICE"
                            >
                                <b>{{ $t('components.help.install') }}</b>
                            </a>
                        </li>
                    </div>
                    <div v-else-if="os=='iOS'">
                        <li>
                            <b>iOS:</b>
                            <a href="https://itunes.apple.com/us/app/flexvdi-client/id1051361263">
                                <b>{{ $t('components.help.install') }}</b>
                            </a>
                        </li>
                    </div>
                </ul>
                <div class="mb-4" v-if="os!='MacOS'">{{ $t('components.help.once-installed') }}</div>
                <h3>{{ $t('components.help.use-browser') }}</h3>
                <hr />
                <i18n path="components.help.no-install" tag="p">
                    <template v-slot:worse-performance>
                        <strong>{{ $t('components.help.worse-performance') }}</strong>
                    </template>
                </i18n>
            </b-container>
        </b-modal>
    </form>
</template>

<script>
// @ is an alias to /src

export default {
  data () {
    return {
      os: this.getOS().os,
      text: this.getOS().text
    }
  },
  methods: {
    getOS () {
      var userAgent = window.navigator.userAgent
      var platform = window.navigator.platform
      var macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K']
      var windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE']
      var iosPlatforms = ['iPhone', 'iPad', 'iPod']
      var os = null
      var text = null

      if (macosPlatforms.indexOf(platform) !== -1) {
        os = 'MacOS'
        text = this.$i18n.components.help.text.macos
      } else if (iosPlatforms.indexOf(platform) !== -1) {
        os = 'iOS'
        text = this.$i18n.components.help.text.ios
      } else if (windowsPlatforms.indexOf(platform) !== -1) {
        os = 'Windows'
        text = this.$i18n.components.help.text.windows
      } else if (/Android/.test(userAgent)) {
        os = 'Android'
        text = this.$i18n.components.help.text.android
      } else if (!os && /Linux/.test(platform)) {
        os = 'Linux'
        text = this.$i18n.components.help.text.linux
      }
      return {
        os: os,
        text: text
      }
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
