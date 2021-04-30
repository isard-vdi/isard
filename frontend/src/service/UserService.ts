import ConnectionService from './ConnectionService';
import { TABLE_PREFIX } from '@/config/constants';
export default class UserService {
  static getUser(params: any): any {
    const query = `query UserDetail($uuid: String) {
      ${TABLE_PREFIX}user(where: {uuid: {_eq: $uuid}}) {
        email
        name
        surname
        id
        uuid
        created_at
      }
    }`;
    return ConnectionService.executeQuery(query, params);
  }
}
