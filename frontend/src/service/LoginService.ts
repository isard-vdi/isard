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
      login (
        usr: "${usr}"
        pwd: "${pwd}"
        provider: "${provider}"
        entityId: "${entityId}"
      )
    }`;

    return ConnectionService.executeMutation(mutation);
  }
}
