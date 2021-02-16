import { villusClient } from '@/main';

export default class LoginService {
  doLogin(usr: string, pwd: string, provider: string, entityId: string): any {
    const loginMutation = `
    mutation LoginMutation {
      login (
        usr: "${usr}"
        pwd: "${pwd}"
        provider: "${provider}"
        entityId: "${entityId}"
      )
    }`;

    return villusClient
      .executeMutation({
        query: loginMutation
      })
      .then((res) => {
        console.log(res);
        return res.data.login;
      });
  }
}
