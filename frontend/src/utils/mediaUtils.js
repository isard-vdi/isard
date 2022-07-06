export class MediaUtils {
  static parseMediaList (items) {
    return items.map((item) => {
      return MediaUtils.parseMedia(item)
    }) || []
  }

  static parseMedia (item) {
    const {
      id,
      name,
      description,
      status,
      owner,
      category,
      group,
      allowed,
      progress
    } = item
    return {
      id,
      name,
      description,
      status,
      owner,
      category,
      group,
      allowed,
      progress
    }
  }
}
