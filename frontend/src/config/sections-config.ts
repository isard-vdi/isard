export interface SectionConfig {
  name: string;
  baseUrl: string;
  query: {
    search: string;
    detail: string;
    update?: string;
    create?: string;
  };
  table: {
    columns: { field: string; header: string }[]; // Plain column
    extraColumnsInludes?: string[]; // Hardcoded columns with templates
  };
  detail?: string;
  defaultValues?: any;
}

export interface SectionModelMap {
  [id: string]: SectionModel;
}

export interface SectionModel {
  config: SectionConfig;
  tabs?: Tabs;
  defaultTab?: string;
  stepper?: any;
  search?: SearchModel;
}

export interface SearchModel {
  cleaner: any;
  apiSegment: string;
}

export interface Tabs {
  [id: string]: TabConfig;
}

export interface TabConfig {
  //tab configuration
}
