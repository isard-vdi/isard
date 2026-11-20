// Single entry point for the apiv4 test fixtures. Importing a domain
// module runs its registerResource() side-effect, so cleanup knows every
// tracked kind regardless of which helpers a spec uses.
import './reservables.js'

export { test, expect, apiv4ClientForPage } from './client.js'
export { unwrap } from './unwrap.js'
export { track, cleanupTrackedResources } from './resources.js'
export {
  waitForDesktopStopped,
  editDesktopWhenStopped,
  getFirstAllowedTemplate,
  createDesktopAndTrack,
} from './desktops.js'
export { createBookingAndTrack, createPlanAndTrack } from './bookings.js'
export {
  E2E_FRONTEND_MODE_RULE_PREFIX,
  listFrontendModeRules,
  findFrontendModeRuleByName,
  nextFrontendModeRulePriority,
  createFrontendModeRuleAndTrack,
  updateFrontendModeRule,
  setFrontendModeRuleAllowed,
  getFrontendModeRuleAllowed,
  purgeE2eFrontendModeRules,
  waitForFrontendMode,
} from './frontendModeRules.js'
