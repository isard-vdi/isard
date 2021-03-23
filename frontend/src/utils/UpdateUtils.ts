import { differenceBy } from 'lodash';

export default class UpdateUtils {
  static getUpdateObject(tgt: any, src: any) {
    if (Array.isArray(tgt)) {
      // if you got array
      return tgt; // just copy it
    }

    // if you got object
    var rst: any = {};
    for (var k in tgt) {
      // visit all fields
      if (typeof src[k] === 'object') {
        // if field contains object (or array because arrays are objects too)
        rst[k] = this.getUpdateObject(tgt[k], src[k]); // diff the contents
        if (Object.keys(rst[k]).length === 0) {
          delete rst[k]; // The object had no properties, so delete that property
        } else if (rst[k].length) {
          if (
            differenceBy(rst[k], src[k], 'id').length === 0 &&
            differenceBy(src[k], rst[k], 'id').length === 0
          ) {
            delete rst[k]; // The array has not changed, don't send
          }
        }
      } else if (src[k] !== tgt[k]) {
        // if field is not an object and has changed
        rst[k] = tgt[k]; // use new value
      }
      // otherwise just skip it
    }
    return rst;
  }

  static buildUpdateMutation(
    mutation: string,
    mutationObject: any
  ): { parsedMutation: string; variables: {} } {
    const parsedMutation: string = mutation;
    const variables: {} = mutationObject;

    return { parsedMutation, variables };
  }
}
