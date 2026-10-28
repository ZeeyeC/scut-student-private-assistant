// The installed Luxon runtime is already used by FullCalendar. Keep the small
// surface used for explicit timezone entry typed without adding a dependency.
declare module "luxon" {
  export class DateTime {
    static fromISO(value: string, options?: { zone?: string }): DateTime;
    readonly isValid: boolean;
    setZone(zone: string): DateTime;
    getPossibleOffsets(): DateTime[];
    toFormat(format: string): string;
    toISO(): string | null;
  }
}
