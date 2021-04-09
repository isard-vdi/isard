namespace Types {
  export interface Entity {
    id: string;
    name: string;
    creationDate: string;
    uuid: string;
    description: string;
    users?: User[];
    //TODO: Añadir atributos
  }
}
