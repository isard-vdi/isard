export class StringUtils {
  static isNullOrUndefinedOrEmpty (arg) {
    return arg === null || arg === undefined || arg === 'undefined' || arg === ''
  }
}
