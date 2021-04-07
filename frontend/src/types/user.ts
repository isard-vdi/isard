namespace Types {
  export interface User {
    id: string;
    name: string;
    surname1: string;
    surname2: string;
    avatar: string;
    profile: string;
    email: string;
    status: string;
    organizationId: string;
    roles: string[];
    lastAttempt: string;
    creationDate: string;
    uuid: string;
    entities?: Entity[];
  }
}
