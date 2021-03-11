import { Client, createClient, defaultPlugins, definePlugin } from 'villus';

export let villusClient: Client;

export default class ConnectionService {
  static executeQuery(query: string, params: Object): any {
    return villusClient
      .executeQuery({
        query: query,
        variables: params
      })
      .then((res) => res.data);
  }

  static executeMutation(query: string) {
    return villusClient.executeMutation({ query }).then((res) => {
      return res.data;
    });
  }

  static authPluginWithConfig = (config: { token: string }) => {
    // opContext will be automatically typed
    return definePlugin(({ opContext }) => {
      // Add auth headers with configurable prefix
      opContext.headers.authorization = `${config.token}`;
    });
  };

  static setClientBackend() {
    villusClient = createClient({
      url: process.env.VUE_APP_REALTIME_URL,
      use: [...defaultPlugins()]
    });
  }

  static setClientHasura(token: string) {
    villusClient = createClient({
      url: process.env.VUE_APP_API_URL,
      use: [
        ConnectionService.authPluginWithConfig({ token }),
        ...defaultPlugins()
      ]
    });
  }
}
