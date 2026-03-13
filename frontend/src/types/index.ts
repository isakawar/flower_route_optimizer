export interface DeliveryStop {
  address: string;
  eta: string; // "10:12"
  driveMin: number;
  waitMin: number;
  lat?: number;
  lng?: number;
  timeStart?: string | null; // "HH:MM" from original order, preserved for recalculation
  timeEnd?: string | null;
}

export interface RecalculateStop {
  lat: number;
  lng: number;
  address: string;
  timeStart?: string | null;
  timeEnd?: string | null;
}

export interface RecalculateRoute {
  courierId: number;
  stops: RecalculateStop[];
}

export interface RecalculateParams {
  routes: RecalculateRoute[];
  depot: { lat: number; lng: number };
}

export interface AddressSuggestion {
  displayName: string;
  city: string;
  region: string;
  country: string;
  lat: number;
  lng: number;
  importance: number;
}

export interface CourierRoute {
  courierId: number;
  stops: DeliveryStop[];
  totalDriveMin: number;
  totalDistanceKm: number;
  suggestedDepartureTime?: string | null; // "HH:MM" when courier should actually leave
  geometry?: [number, number][] | null; // [[lat, lng], ...] road path from OSRM
}

export interface OptimizationResult {
  routes: CourierRoute[];
  stats: {
    totalDeliveries: number;
    totalDriveMin: number;
    totalDistanceKm: number;
    numCouriers: number;
  };
  depot: { lat: number; lng: number };
}

export type AppState = "idle" | "loading" | "complete" | "error";

export interface OptimizationParams {
  csvFile: File;
}

export interface ProgressStep {
  id: string;
  label: string;
  status: "pending" | "active" | "complete";
}

export const COURIER_COLORS = [
  "#d4a5bf", // rose
  "#c9a96e", // gold
  "#8b9dd4", // periwinkle
  "#7dcfb0", // mint
  "#d48b8b", // coral
  "#a88bd4", // lavender
  "#8bd4c0", // teal
  "#d4c48b", // wheat
] as const;
