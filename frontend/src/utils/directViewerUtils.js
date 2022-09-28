import i18n from '@/i18n'
import { DateUtils } from './dateUtils'

export class DirectViewerUtils {
  static parseDirectViewer (item) {
    const { vmName: name, vmDescription: description, viewers, vmState: state, scheduled, jwt, desktopId } = item
    return {
      name,
      description,
      viewers,
      state,
      shutdown: scheduled.shutdown ? i18n.t('message-modal.messages.desktop-time-limit', { name: name, date: DateUtils.formatAsTime(DateUtils.utcToLocalTime(scheduled.shutdown)) }) : false,
      jwt,
      desktopId
    }
  }
}
