import type { components } from "./generated-api";
import type { CampusPresetId } from "./CampusPresetSelector";
// Aggregate payloads are validated per kind by the server; generated envelope is shared.
export type Resource = Omit<components["schemas"]["ResourceView"], "data"> & {
  data: Record<string, any>;
};
export type Course = components["schemas"]["Course"];
export type SettingsData = components["schemas"]["StudentSettings"] & {
  campus_preset?: CampusPresetId | null;
};
export type Timetable = components["schemas"]["Timetable"] & {
  campus_preset?: CampusPresetId | null;
};
