export interface Permit {
  city_id: string;
  permit_number: string;
  address: string;
  issue_date: string;
  contractor_name?: string | null;
  valuation?: number | null;
  location?: { type: "Point"; coordinates: [number, number] } | null;
}

export interface City {
  slug: string;
  name: string;
  strategy: string;
  auto_send: boolean;
  status: string;
}

export interface Filters {
  city: string;
  yearMin: string;
  yearMax: string;
  contractor: string;
}
