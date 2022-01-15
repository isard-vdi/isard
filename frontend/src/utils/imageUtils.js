export class ImageUtils {
  static parseImages (items) {
    return items.map((item) => {
      return ImageUtils.parseImage(item)
    }) || []
  }

  static parseImage (item) {
    const { id, type, url } = item
    return {
      id,
      type,
      url
    }
  }
}
