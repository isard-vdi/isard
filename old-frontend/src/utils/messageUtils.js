import i18n from '@/i18n'
import { StringUtils } from '../utils/stringUtils'
import { DateUtils } from './dateUtils'

const TYPES_BY_SEVERITY = ['info', 'warning', 'danger']

export class MessageUtils {
  static parseMessage (item) {
    const { type, msg_code: messageCode, params } = item
    if (params.date) {
      // params.fromnow = DateUtils.dateToMoment(DateUtils.utcToLocalTime(params.date)).fromNow(true)
      params.date = DateUtils.formatAsTime(DateUtils.utcToLocalTime(params.date))
    }
    const message = i18n.t(`message-modal.messages.${messageCode}`, params)
    return {
      key: `${messageCode}|${params.desktop_id || message}`,
      type,
      message,
      msgCode: messageCode,
      desktopId: params.desktop_id || null,
      extendEnabled: params.extend_enabled || false,
      extendTime: params.extend_time || 0
    }
  }

  static highestType (messages) {
    return messages.reduce((highest, message) => {
      return TYPES_BY_SEVERITY.indexOf(message.type) >= TYPES_BY_SEVERITY.indexOf(highest) ? message.type : highest
    }, messages.length ? messages[0].type : undefined)
  }

  static textColor (type) {
    return StringUtils.isNullOrUndefinedOrEmpty(type) ? 'default' : 'light'
  }
}
