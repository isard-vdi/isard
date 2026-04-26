import { DesktopUtils } from './desktopsUtils'
import { DateUtils } from './dateUtils'

export class DeploymentsUtils {
  static parseDeployments (items) {
    return items.map((item) => {
      return DeploymentsUtils.parseDeploymentsItem(item)
    }) || []
  }

  static parseDeploymentsItem (deployment) {
    // apiv4 OwnedDeployment shape: snake_case fields + desktop_names (plural list)
    // + tag_visible. Vue 2 has always read camelCase + a single desktopName.
    // Map apiv4 → Vue 2 here; multi-desktop deployments display the count.
    const {
      id,
      name,
      description,
      visible_desktops: visibleDesktops,
      started_desktops: startedDesktops,
      total_desktops: totalDesktops,
      tag_visible: visible,
      needs_booking: needsBooking,
      desktop_names: desktopNames
    } = deployment
    const isMultiDesktop = Array.isArray(desktopNames) && desktopNames.length > 1
    return {
      id,
      name,
      description,
      visibleDesktops,
      startedDesktops,
      totalDesktops,
      creatingDesktops: 0,
      visible,
      needsBooking,
      desktopName: isMultiDesktop ? `${desktopNames.length} desktop types` : (desktopNames && desktopNames[0]) || '',
      template: isMultiDesktop ? '' : (desktopNames && desktopNames[0]) || '',
      isMultiDesktop
    }
  }

  static parseDeployment (deployment) {
    // apiv4 uses tag_visible at the deployment root; old-frontend has always
    // read `visible`. Accept either so this parser works on the apiv4 wire
    // shape without a per-call adapter.
    const { id, name, desktop_name: desktopName, description, tag_visible: tagVisible, visible: legacyVisible, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId, total_desktops: totalDesktops, total_users: totalUsers, desktops_each_user: desktopsEachUser } = deployment
    const visible = tagVisible !== undefined ? tagVisible : legacyVisible
    const desktops = deployment.desktops
      ? deployment.desktops.map((desktop) => {
        return DeploymentsUtils.parseDeploymentDesktop(desktop)
      })
      : []
    return {
      id,
      name,
      desktops,
      description,
      desktopName,
      visible,
      needsBooking,
      bookingId,
      nextBookingStart: nextBookingStart ? DateUtils.utcToLocalTime(nextBookingStart) : '',
      nextBookingEnd: nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : '',
      totalDesktops,
      totalUsers,
      desktopsEachUser
    }
  }

  static parseDeploymentDesktop (desktop) {
    const { id, ip, name, user, user_name: userName, user_photo: userPhoto, category_name: categoryName, group_name: groupName, state, viewer, viewers, image, accessed, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId, visible, tag } = desktop
    return {
      id,
      ip,
      name,
      user,
      userName,
      userPhoto,
      categoryName,
      groupName,
      image,
      state,
      viewer,
      viewers,
      buttonIconName: desktop.state ? DesktopUtils.buttonIconName(desktop) : '',
      last: accessed,
      bookingId,
      needsBooking,
      nextBookingStart: nextBookingStart ? DateUtils.utcToLocalTime(nextBookingStart) : '',
      nextBookingEnd: nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : '',
      visible,
      tag
    }
  }
}
