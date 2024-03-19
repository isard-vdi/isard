<template>
  <b-container
    id="content"
    fluid
  >
    <span
      class="d-flex justify-content-between align-items-center"
    >
      <h5 class="font-weight-bold mb-0">
        <b-iconstack
          v-if="deployment.needsBooking"
          font-scale="1"
          role="button"
          :title="$t('components.desktop-cards.actions.booking')"
          @click="onClickBookingDesktop(deployment)"
        >
          <b-icon
            stacked
            icon="calendar"
            variant="warning"
          />
          <b-icon
            stacked
            icon="exclamation-triangle-fill"
            scale="0.5"
            shift-v="-1"
            variant="warning"
          />
        </b-iconstack>
        {{ deployment.name }}
        <b-badge
          v-if="deployment.needsBooking"
          class="ml-2"
          variant="warning"
        >
          {{ bookingBadge }}
        </b-badge>
      </h5>
      <p
        class="text-muted mb-0"
      >
        {{ desktopsBadge }} | {{ startedBadge }} | {{ visibleBadge }}
      </p>
    </span>
    <hr class="mb-0">
    <DeploymentDesktopsList
      :desktops="sortedDesktops"
      :loading="!getDeploymentLoaded"
      :visible="deployment.visible"
    />
  </b-container>
</template>
<script>
// @ is an alias to /src
import DeploymentDesktopsList from '@/components/deployments/DeploymentDesktopsList.vue'
import { mapGetters } from 'vuex'
import { desktopStates } from '@/shared/constants'
import { computed } from '@vue/composition-api'
import { DateUtils } from '@/utils/dateUtils'
import i18n from '@/i18n'

export default {
  components: {
    DeploymentDesktopsList
  },
  setup (props, context) {
    const $store = context.root.$store

    const deployment = computed(() => $store.getters.getDeployment)
    const badgeVariant = computed(() => deployment.value.visible ? 'success' : 'danger')

    const deploymentVariant = computed(() => deployment.value.visible ? 'visibleHighlight' : 'alert-danger')

    const badgeText = computed(() => deployment.value.visible ? i18n.t('views.deployment.visibility.visible') : i18n.t('views.deployment.visibility.not-visible'))

    const onClickBookingDesktop = (deployment) => {
      const data = { id: deployment.id, type: 'deployment', name: deployment.name }
      $store.dispatch('goToItemBooking', data)
    }

    const bookingBadge = computed(() => {
      if (DateUtils.dateIsAfter(deployment.value.nextBookingEnd, new Date()) && DateUtils.dateIsBefore(deployment.value.nextBookingStart, new Date())) {
        return i18n.t('components.desktop-cards.notification-bar.booking-ends') + DateUtils.formatAsTime(deployment.value.nextBookingEnd) + ' ' + DateUtils.formatAsDayMonth(deployment.value.nextBookingEnd)
      } else if (deployment.value.nextBookingStart) {
        return i18n.t('components.desktop-cards.notification-bar.next-booking') + ': ' + DateUtils.formatAsTime(deployment.value.nextBookingStart) + ' ' + DateUtils.formatAsDayMonth(deployment.value.nextBookingStart)
      } else {
        return i18n.t('components.desktop-cards.notification-bar.no-next-booking')
      }
    })

    const desktopsBadge = computed(() => {
      return i18n.t('views.deployment.desktop.desktops') + ': ' + deployment.value.desktops.length
    })
    const startedBadge = computed(() => {
      return i18n.t('views.deployment.desktop.started') + ': ' + deployment.value.desktops.filter(d => [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase())).length
    })
    const visibleBadge = computed(() => {
      return i18n.t('views.deployment.desktop.visible') + ': ' + deployment.value.desktops.filter(d => d.visible).length
    })

    return {
      deployment,
      badgeVariant,
      badgeText,
      deploymentVariant,
      onClickBookingDesktop,
      bookingBadge,
      desktopsBadge,
      startedBadge,
      visibleBadge
    }
  },
  computed: {
    ...mapGetters(['getDeployment', 'getDeploymentLoaded']),
    sortedDesktops () {
      return this.getDeployment.desktops.slice().sort(d => {
        // return started desktops first
        return [desktopStates.started, desktopStates.waitingip].includes(d.state.toLowerCase()) ? -1 : 1
      })
    }
  },
  created () {
    this.$store.dispatch('fetchDeployment', { id: this.$route.params.id })
  },
  destroyed () {
    this.$store.dispatch('resetDeploymentsState')
  }
}
</script>
