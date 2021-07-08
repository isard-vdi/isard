<template>
  <div>
    <b-card no-body class="mt-4 mb-2">
      <template v-slot:header>
        <small class="text-muted">{{ desktop.user }}</small>
      </template>
      <b-card-body class="pt-0 pb-0 pl-0 pr-0" @click="$refs.viewer.show()" ref="screen" :style='`height: ${this.height}; cursor: pointer;`'/>
    </b-card>
    <b-modal @shown="takeOver" id="viewer"  size="xl" content-class="shadow" centered ref="viewer" :title="desktop.user"
    hide-footer body-class="pt-0 pb-0 pl-0 pr-0"/>
  </div>
</template>

<script>
import RFB from '@novnc/novnc/core/rfb'

export default {
  props: {
    height: {
      type: String,
      required: true
    },
    desktop: {
      type: Object,
      required: true
    }
  },
  methods: {
    newRFB (target, viewOnly, qualityLevel) {
      var viewerData = this.desktop.viewers.filter(viewer => viewer.type === 'browser')[0]
      this.rfb = new RFB(target, 'wss://' + viewerData.host + ':' + viewerData.port + '/' + viewerData.vmHost + '/' + viewerData.vmPort, {
        credentials: { password: viewerData.token }
      })

      this.rfb.viewOnly = viewOnly
      this.rfb.qualityLevel = qualityLevel
      this.rfb.scaleViewport = true
    },
    takeOver () {
      this.$refs.viewer.$refs.body.style.height = '750px'
      this.newRFB(this.$refs.viewer.$refs.body, false, 6)
    }
  },
  mounted () {
    this.newRFB(this.$refs.screen, true, 0)
  }
}
</script>
