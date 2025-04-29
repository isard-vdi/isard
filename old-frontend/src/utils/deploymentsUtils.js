import { DesktopUtils } from './desktopsUtils'
import { DateUtils } from './dateUtils'

export class DeploymentsUtils {
  static parseDeployments (items) {
    return items.map((item) => {
      return DeploymentsUtils.parseDeploymentsItem(item)
    }) || []
  }

  static parseDeploymentsItem (deployment) {
    const { id, name, description, visibleDesktops, startedDesktops, totalDesktops, creatingDesktops, visible, needs_booking: needsBooking, desktop_name: desktopName, template } = deployment
    return {
      id,
      name,
      description,
      visibleDesktops,
      startedDesktops,
      totalDesktops,
      creatingDesktops,
      visible,
      needsBooking,
      desktopName,
      template
    }
  }

  static parseDeployment (deployment) {
    const { id, name, desktop_name: desktopName, description, visible, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId } = deployment
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
      nextBookingEnd: nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : ''
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
