import UsersUtils from '@/utils/UsersUtils';

export class SearchUserParser {
  static parse(items: any[]) {
    return UsersUtils.cleanUsers(items);
  }
}
