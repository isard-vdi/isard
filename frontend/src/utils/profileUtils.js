export class ProfileUtils {
  static parseProfile (item) {
    const { category, email, group, name, provider, quota, used, restriction_applied: restrictionApplied, role, username, photo } = item
    return {
      category,
      email,
      group,
      name,
      provider,
      used,
      quota,
      restrictionApplied,
      role,
      username,
      photo
    }
  }
}
