import { sections } from '@/config/sections';
import { villusClient } from '@/main';
import { useQuery } from 'villus';
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
