import { DateUtils } from '@/utils/dateUtils'
import i18n from '@/i18n'

export class PlanningUtils {
  static parseEvents (items) {
    return items.map((item) => {
      return PlanningUtils.parseEvent(item)
    }) || []
  }

  static parseEvent (item) {
    const { id, start, end, units, subitem_id: subitemId } = item
    return {
      id,
      start: DateUtils.utcToLocalTime(start),
      end: DateUtils.utcToLocalTime(end),
      title: `${subitemId} (${units} ${i18n.t('components.bookings.item.units')})`,
      class: 'unavailable',
      subitemId: subitemId
    }
  }

  static parseItems (items) {
    return items.map((item) => {
      return PlanningUtils.parseItem(item)
    }) || []
  }

  static parseItem (item) {
    const { id, name, model, brand, description } = item
    return {
      id,
      name,
      model,
      brand,
      description
    }
  }

  static parseSubitems (items) {
    return items.map((item) => {
      return PlanningUtils.parseSubitem(item)
    }) || []
  }

  static parseSubitem (item) {
    const { id, name, profile, units, description } = item
    return {
      id,
      name,
      description,
      profile,
      units
    }
  }
}
