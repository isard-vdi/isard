<template>
  <form>
    <b-modal
      id="rdp_help_modal"
      ref="rdp_help_modal"
      size="lg"
      content-class="shadow"
      centered
      :ok-title="$t('views.direct-viewer.help.rdp.close-guide')"
      ok-only
      hide-header
    >
      <b-container class="text-left">
        <h3>
          {{ $t('views.direct-viewer.help.rdp.local-client') }}
        </h3>
        <hr>
        <b>{{ $t('views.direct-viewer.help.rdp.included') }}</b>
        {{ $t('views.direct-viewer.help.rdp.client-required') }}

        <b-row class="justify-content-md-center">
          <b-button
            variant="outline-primary"
            class="my-4"
            :href="getConfig.viewersDocumentationUrl"
          >
            {{ $t('views.direct-viewer.help.rdp.download-install') }}
          </b-button>
        </b-row>

        <div class="mb-4">
          {{ $t('views.direct-viewer.help.rdp.once-installed') }}
        </div>
      </b-container>
    </b-modal>
  </form>
</template>

<script>
import { mapGetters } from 'vuex'

export default {
  computed: {
    ...mapGetters([
      'getConfig'
    ])
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
