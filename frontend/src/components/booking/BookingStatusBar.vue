<template>
  <div
    id="statusbar"
    class="px-0 px-lg-5 pl-2"
  >
    <b-container
      fluid
      class="px-0"
    >
      <b-navbar
        toggleable="lg"
        type="light"
        variant=""
      >
        <div class="separator" />
        <div class="d-flex flex-grow">
          <b-navbar-nav
            id="statusbar-content"
            class="flex-grow flex-row"
          >
            <b-nav-item disabled>
              <span class="d-none d-lg-inline text-medium-gray">{{ `${$t("components.bookings.item.status-bar.forbid-time")}:` }}</span><span class="text-medium-gray">{{ ` ${priority.forbidTime} min` }}</span>
            </b-nav-item>
            <b-nav-item disabled>
              <span class="d-none d-lg-inline text-medium-gray">{{ `${$t("components.bookings.item.status-bar.max-time")}:` }}</span><span class="text-medium-gray">{{ ` ${priority.maxTime} min` }}</span>
            </b-nav-item>
            <b-nav-item disabled>
              <span class="d-none d-lg-inline text-medium-gray">{{ `${$t("components.bookings.item.status-bar.max-items")}:` }}</span><span class="text-medium-gray">{{ ` ${priority.maxItems}` }}</span>
            </b-nav-item>
          </b-navbar-nav>

          <!-- Right aligned nav items-->
          <b-navbar-nav
            v-if="item.id"
            class="ml-auto flex-row"
          >
            <div class="pt-1">
              <b-button
                :pill="true"
                class="mr-0 mr-md-4"
                variant="outline-primary"
                size="sm"
                @click="createEvent()"
              >
                {{ $t("components.bookings.item.status-bar.buttons.add-booking") }}
              </b-button>
            </div>
          </b-navbar-nav>
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>
<script>
import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const item = computed(() => $store.getters.getBookingItem)

    const priority = computed(() => $store.getters.getBookingPriority)

    // Create Event
    const createEvent = (event) => {
      $store.dispatch('showBookingModal', true)
      $store.dispatch('eventModalData', {
        type: 'create'
      })
    }

    return { createEvent, priority, item }
  }
}
</script>
