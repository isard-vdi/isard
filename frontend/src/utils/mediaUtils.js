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
    return {
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
  }
}
