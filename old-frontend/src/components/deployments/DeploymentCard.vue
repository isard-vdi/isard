<template>
  <b-col cols="3">
    <b-card
      no-body
      class="mt-4 mb-2 mx-3"
    >
      <template #header>
        <b-row class="pt-2 pl-3 pr-3">
          <b-avatar
            :src="desktop.userPhoto"
            size="sm"
            referrerPolicy="no-referrer"
            class="mr-2"
          />
          <h6
            cols="10"
            class="text-muted pt-1"
          >
            {{ desktop.userName }}
          </h6>
          <b-icon
            cols="2"
            icon="arrows-fullscreen"
            scale="1.25"
            class="cursor-pointer ml-auto flex-row d-none d-xl-flex"
            @click="selectDesktop(desktop)"
          />
        </b-row>
      </template>
      <b-card-body
        class="pt-0 pb-0 pl-0 pr-0"
        @click="selectDesktop(desktop)"
      >
        <NoVNC
          v-if="desktop.viewer"
          :height="'200px'"
          :desktop="desktop"
          :view-only="true"
          :quality-level="0"
        />
        <div
          v-else
          style="height: 200px; background-color: black; padding-top: 50px"
          class="cursor-pointer"
        >
          <div
            id="deployment-logo"
            class="rounded-circle bg-red mx-auto d-block align-items-center "
            style="background-image: url(/custom/logo.svg);background-size: 70px 70px; opacity: 0.5;"
          />
          <p class="text-center text-white">
            {{ $t('views.deployment.desktop.not-available') }}
          </p>
        </div>
      </b-card-body>
    </b-card>
  </b-col>
</template>
<script>
import NoVNC from '@/components/NoVNC.vue'

export default {
  components: {
    NoVNC
  },
  props: {
    desktop: {
      required: true,
      type: Object
    }
  },
  methods: {
    selectDesktop (desktop) {
      this.$store.dispatch('setSelectedDesktop', desktop)
      this.$store.dispatch('setViewType', 'youtube')
    }
  }
}
</script>
