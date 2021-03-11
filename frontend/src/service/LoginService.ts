import ConnectionService from './ConnectionService';
export default class LoginService {
  static doLogin(
    usr: string,
    pwd: string,
    provider: string,
    entityId: string
  ): any {
    const mutation = `
    mutation LoginMutation {
      login (input: {
        usr: "${usr}",
        pwd: "${pwd}",
        provider: "${provider}",
        entityId: "${entityId}"
      }){
        id
        name
        token
        surname
      }
    }`;

    return ConnectionService.executeMutation(mutation);
  }
}
