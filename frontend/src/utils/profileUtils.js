export class ProfileUtils {
  static parseProfile (item) {
    const { category, email, group, name, provider, quota, role, username, photo } = item
    return {
      category,
      email,
      group,
      name,
      provider,
      quota,
      role,
      username,
      photo
    }
  }
}
