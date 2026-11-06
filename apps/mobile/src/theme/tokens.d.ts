export type ParkingStatus = "available" | "conditional" | "restricted";

export declare const color: {
  ink: string;
  paper: string;
  steel: string;
  line: string;
  brand: string;
  status: Record<ParkingStatus, string>;
  map: { lotFill: string; halo: string; clusterText: string };
};

export declare const fontSize: Record<"xs" | "sm" | "base" | "md" | "lg" | "xl" | "2xl", number>;
export declare const spacing: Record<1 | 2 | 2.5 | 3 | 3.5 | 4 | 5 | 6 | 8, number>;
export declare const radius: Record<"sm" | "md" | "lg" | "xl" | "full", number>;
export declare const touchTarget: { min: number; driving: number };
