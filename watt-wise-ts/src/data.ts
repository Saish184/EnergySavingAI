/**
 * Only static facts needed before sign-in: the flat ids for the login form (from flats.csv).
 * Everything else (consumption, findings, savings, scores) is loaded from the backend engine.
 */
export const FLATS: readonly { id: string; residents: number; areaM2: number }[] = [
  { id: 'F001', residents: 2, areaM2: 56 },
  { id: 'F002', residents: 3, areaM2: 69 },
  { id: 'F003', residents: 4, areaM2: 82 },
  { id: 'F004', residents: 2, areaM2: 56 },
  { id: 'F005', residents: 5, areaM2: 95 },
  { id: 'F006', residents: 3, areaM2: 69 },
  { id: 'F007', residents: 4, areaM2: 82 },
  { id: 'F008', residents: 2, areaM2: 56 },
];
