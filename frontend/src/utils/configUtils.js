export class ConfigUtils {
  static parseConfig (config) {
    const {
      show_admin_button: showAdminButton,
      show_bookings_button: showBookingsButton,
      documentation_url: documentationUrl,
      show_temporal_tab: showTemporalTab
    } = config
    return {
      showAdminButton,
      showBookingsButton,
      documentationUrl,
      showTemporalTab
    }
  }
}
