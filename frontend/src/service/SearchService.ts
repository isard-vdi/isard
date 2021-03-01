import { sections } from '@/config/sections';
import { villusClient } from '@/main';
import { useQuery } from 'villus';

export default class SearchService {
  listSearch(
    query: string,
    queryParams: string[],
    size: number,
    start: number
  ): any {
    return villusClient
      .executeQuery({
        query: query
      })
      .then((res) => res.data.user);
  }
}
