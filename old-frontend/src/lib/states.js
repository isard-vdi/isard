export default {
  /**
   * The Guacamole connection has not yet been attempted.
   *
   * @type String
   */
  IDLE: 'IDLE',

  /**
   * The Guacamole connection is being established.
   *
   * @type String
   */
  CONNECTING: 'CONNECTING',

  /**
   * The Guacamole connection has been successfully established, and the
   * client is now waiting for receipt of initial graphical data.
   *
   * @type String
   */
  WAITING: 'WAITING',

  /**
   * The Guacamole connection has been successfully established, and
   * initial graphical data has been received.
   *
   * @type String
   */
  CONNECTED: 'CONNECTED',

  /**
   * The Guacamole connection has terminated successfully. No errors are
   * indicated.
   *
   * @type String
   */
  DISCONNECTED: 'DISCONNECTED',

  /**
   * The Guacamole connection has terminated due to an error reported by
   * the client. The associated error code is stored in statusCode.
   *
   * @type String
   */
  CLIENT_ERROR: 'CLIENT_ERROR',

  /**
   * The Guacamole connection has terminated due to an error reported by
   * the tunnel. The associated error code is stored in statusCode.
   *
   * @type String
   */
  TUNNEL_ERROR: 'TUNNEL_ERROR',

  /**
   * The Guacamole connection can't be established since the needed cookie
   * is missing.
   *
   * @type String
   */
  COOKIE_ERROR: 'COOKIE_ERROR',

  /**
   * The Guacamole connection can't be established since the needed cookie is
   * expired.
   *
   * @type String
   */
  COOKIE_EXPIRED: 'COOKIE_EXPIRED',

  /**
   * The Guacamole connection has terminated due to an error in the client
   * The associated error code is stored in statusCode.
   *
   * @type String
   */
  RETRYING: 'RETRYING',

  /**
   * The Guacamole connection cannot be established because the desktop does not
   * have the RDP feature enabled or it is not running.
   *
   * @type String
   */
  RDP_NOT_RUNNING: 'RDP_NOT_RUNNING'
}
