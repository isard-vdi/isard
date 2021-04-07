import DesktopsUtils from '@/utils/DesktopsUtils';

export class SearchDesktopsParser {
  static parse(items: any[]) {
    return DesktopsUtils.cleanDesktops(items);
  }
}
