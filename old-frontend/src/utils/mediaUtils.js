
export class MediaUtils {
  static parseMediaList (items) {
    return items.filter((item) => {
      return item.status !== 'deleted'
    }).map((item) => {
      return MediaUtils.parseMedia(item)
    }) || []
  }

  static parseMedia (item, { partial = false } = {}) {
    // ``partial`` keeps only keys present in the payload so a
    // change-handler ``media_update`` (emitted with
    // ``model_dump(exclude_none=True)``) doesn't clobber cached
    // ``description`` / ``allowed`` / ``progress`` with ``undefined``.
    const {
      id,
      name,
      description,
      status,
      user,
      user_name: userName,
      category,
      category_name: categoryName,
      group,
      group_name: groupName,
      allowed,
      progress,
      kind,
      editable
    } = item
    const out = {
      id,
      name,
      description,
      status,
      user,
      userName,
      category,
      categoryName,
      group,
      groupName,
      allowed,
      progress,
      kind,
      editable
    }
    if (!partial) return out
    return Object.fromEntries(Object.entries(out).filter(([, v]) => v !== undefined))
  }

  static parseMediaDesktops (items) {
    return items.map((item) => {
      return MediaUtils.parseMediaDesktop(item)
    }) || []
  }

  static parseMediaDesktop (item) {
    const {
      id,
      name,
      kind,
      status,
      user,
      user_name: userName
    } = item
    return {
      id,
      name,
      kind,
      status,
      user,
      userName
    }
  }
}
