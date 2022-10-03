export class ConfigUtils {
  static parseConfig (config) {
    const {
      show_bookings_button: showBookingsButton,
      documentation_url: documentationUrl,
      show_temporal_tab: showTemporalTab,
      quota
    } = config
    return {
      showBookingsButton,
      documentationUrl,
      showTemporalTab,
      quota
    }
  }
}
