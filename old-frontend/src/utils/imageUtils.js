export class ImageUtils {
  static parseImages (items) {
    return (items || []).map((item) => ImageUtils.parseImage(item))
  }

  static parseImage (item) {
    const { id, type, url } = item
    return {
      id,
      type,
      url: ImageUtils.normalizeImageUrl({ id, type, url })
    }
  }

  static normalizeImageUrl ({ id, type, url }) {
    let imageUrl = url || ''

    if (!imageUrl && id && type) {
      imageUrl = `/assets/img/desktops/${type}/${id}`
    } else if (imageUrl.endsWith('/') && id) {
      imageUrl = `${imageUrl}${id}`
    } else if (id && imageUrl.startsWith('/assets/img/desktops/') && !imageUrl.includes(id)) {
      imageUrl = `${imageUrl.replace(/\/+$|\/$/, '')}/${id}`
    }

    return imageUrl
  }
}
