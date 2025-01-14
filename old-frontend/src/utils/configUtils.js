export class ConfigUtils {
  static parseConfig (config) {
    const {
      show_bookings_button: showBookingsButton,
      documentation_url: documentationUrl,
      viewers_documentation_url: viewersDocumentationUrl,
      show_temporal_tab: showTemporalTab,
      show_change_email_button: showChangeEmailButton,
      http_port: httpPort,
      https_port: httpsPort,
      bastion_ssh_port: bastionSshPort,
      can_use_bastion: canUseBastion,
      migrations_block: migrationsBlock
    } = config
    return {
      showBookingsButton,
      documentationUrl,
      viewersDocumentationUrl,
      showTemporalTab,
      showChangeEmailButton,
      httpPort,
      httpsPort,
      bastionSshPort,
      canUseBastion,
      migrationsBlock
    }
  }
}
