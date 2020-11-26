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
                <div v-if="os=='Windows'">
                    {{ $t('components.help.text.windows') }}
                    <ul v-on:click.stop>
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
                    {{ $t('components.help.text.linux') }}
                    <ul v-on:click.stop>
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
                <div v-else-if="os=='Android'">
                    {{ $t('components.help.text.android') }}
                    <ul v-on:click.stop>
                        <li>
                            <b>Android:</b>
                            <a
                                href="https://play.google.com/store/apps/details?id=com.iiordanov.freeaSPICE"
                            >
                                <b>{{ $t('components.help.install') }}</b>
                            </a>
                        </li>
                    </ul>
                </div>
                <div v-else-if="os=='iOS'">
                    {{ $t('components.help.text.ios') }}
                    <ul v-on:click.stop>
                        <li>
                            <b>iOS:</b>
                            <a href="https://itunes.apple.com/us/app/flexvdi-client/id1051361263">
                                <b>{{ $t('components.help.install') }}</b>
                            </a>
                        </li>
                    </ul>
                </div>
                <div v-else-if="os=='MacOS'">
                    {{ $t('components.help.text.macos') }}
                </div>
                <div class="mb-4" v-if="os!='MacOS'">{{ $t('components.help.once-installed') }}</div>
                <h3>{{ $t('components.help.use-browser') }}</h3>
                <hr />
                {{ $t('components.help.no-install') }}
                <b>{{ $t('components.help.worse-performance') }}</b>
                . {{$t('components.help.simply') }}
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
      var userAgent = window.navigator.userAgent
      var platform = window.navigator.platform
      var macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K']
      var windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE']
      var iosPlatforms = ['iPhone', 'iPad', 'iPod']
      var os = null

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
