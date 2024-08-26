import i18n from '@/i18n'
import { StringUtils } from '../utils/stringUtils'
import { DateUtils } from './dateUtils'

export class MessageUtils {
  static parseMessage (item) {
    const { type, msg_code: messageCode, params } = item
    if (params.date) {
      // params.fromnow = DateUtils.dateToMoment(DateUtils.utcToLocalTime(params.date)).fromNow(true)
      params.date = DateUtils.formatAsTime(DateUtils.utcToLocalTime(params.date))
    }
    return {
      type,
      textColor: StringUtils.isNullOrUndefinedOrEmpty(type) ? 'default' : 'light',
      message: i18n.t(`message-modal.messages.${messageCode}`, params),
      show: true
    }
  }
}
