import { villusClient } from '@/main';

export default class SearchService {
  listSearch(section: string, query: string, queryParams: string[]): any {
    const usersQuery: string = `
    query Users {
      user {
        created_at
        email
        id
        name
        surname
        username
        uuid
      }
    }`;

    return villusClient
      .executeQuery({
        query: usersQuery
      })
      .then((res) => res.data.user);
  }
}
