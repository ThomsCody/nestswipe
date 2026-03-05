export interface User {
  id: number;
  email: string;
  name: string;
  picture?: string;
  household_id: number;
}

export interface Listing {
  id: number;
  source: string;
  title: string;
  description?: string;
  price?: number;
  sqm?: number;
  price_per_sqm?: number;
  bedrooms?: number;
  rooms?: number;
  floor?: number;
  city?: string;
  district?: string;
  location_detail?: string;
  external_url?: string;
  photos: ListingPhoto[];
  price_history?: PriceHistoryEntry[];
  last_seen_at?: string;
}

export interface ListingPhoto {
  id: number;
  s3_key: string;
  position: number;
}

export interface Favorite {
  id: number;
  listing: Listing;
  created_at: string;
  comments: Comment[];
}

export interface Comment {
  id: number;
  user_id: number;
  user_name: string;
  body: string;
  created_at: string;
}

export interface PriceHistoryEntry {
  price: number;
  observed_at: string;
}
