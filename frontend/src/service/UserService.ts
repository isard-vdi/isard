import axios from "axios";

export default class UserService {
  getUsers(): Promise<Types.User[]> {
    return axios.get("assets/mockdata/users.json").then(res => res.data.users);
  }

  getUser(): Promise<Types.User> {
    return axios.get("assets/mockdata/users.json").then(res => res.data);
  }
}
