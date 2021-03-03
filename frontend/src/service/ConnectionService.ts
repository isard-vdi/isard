import { villusClient } from '@/main';

export default class ConnectionService {
  static executeQuery(query: string): any {
    return villusClient
      .executeQuery({
        query: query
      })
      .then((res) => res.data);
  }

  static executeMutation(query: string) {
    return villusClient.executeMutation({ query }).then((res) => {
      return res.data;
    });
  }
}
