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
      bastion_domain: bastionDomain,
      bastion_ssh_port: bastionSshPort,
      can_use_bastion: canUseBastion,
      can_use_bastion_individual_domains: canUseBastionIndividualDomains,
      migrations_block: migrationsBlock,
      session: {
        id = '',
        max_renew_time: maxRenewTime = 0,
        max_time: maxTime = 0
      } = {}
    } = config
    return {
      showBookingsButton,
      documentationUrl,
      viewersDocumentationUrl,
      showTemporalTab,
      showChangeEmailButton,
      httpPort,
      httpsPort,
      bastionDomain,
      bastionSshPort,
      canUseBastion,
      canUseBastionIndividualDomains,
      migrationsBlock,
      session: {
        id,
        maxRenewTime,
        maxTime
      }
    }
  }
}
