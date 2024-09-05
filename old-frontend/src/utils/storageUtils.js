export class StorageUtils {
  static parseStorageList (items) {
    return items.map((item) => {
      return StorageUtils.parseStorage(item)
    }) || []
  }

  static parseStorage (item) {
    const {
      id,
      domains,
      actual_size: actualSize,
      virtual_size: virtualSize,
      last,
      user_name: userName
    } = item
    return {
      id,
      domains,
      actualSize,
      virtualSize,
      percentage: Math.round(actualSize * 100 / virtualSize),
      last,
      userName,
      quantityDomains: domains.length
    }
  }

  static parseDomain (item) {
    const {
      id,
      name
    } = item
    return {
      id,
      name
    }
  }
}
