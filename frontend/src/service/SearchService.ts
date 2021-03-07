import ConnectionService from './ConnectionService';

export default class SearchService {
  static listSearch(
    query: string,
    queryParams: string[],
    size: number,
    start: number
  ): any {
    return ConnectionService.executeQuery(query);
  }
}
