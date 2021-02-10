import { User } from '@/store/state';

export default class UsersUtils {
  static cleanUsers(items: any[]): User[] {
    // type as UserSearchItem
    return items.map(
      (item: any): User => {
        return {
          userName: '',
          email: '',
          name: '',
          surname1: '',
          surname2: '',
          status: '',
          organizationId: '',
          roles: [],
          lastAttempt: '',
          creationDate: ''
        };
      }
    );
  }
}
