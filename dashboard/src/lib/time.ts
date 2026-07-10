/**
 * Time display helpers — every ABSOLUTE time shown in the UI goes through here.
 *
 * Times render in the viewer's timezone with the short zone name appended, so
 * a reading is never ambiguous ("3:05:12 PM CDT"). One special case: privacy
 * browser modes (e.g. Firefox resistFingerprinting) report plain "UTC" as the
 * timezone, which would show every clock five-plus hours off for US viewers —
 * when the browser claims bare UTC we fall back to the site's home timezone
 * instead. (Genuine UTC-zone viewers are overwhelmingly servers, not fans.)
 *
 * Wire note: protobuf int64 timestamps arrive as JSON strings — everything
 * here Number()-coerces before formatting.
 */

const HOME_TZ = 'America/Chicago'

/** The timezone all absolute times display in. Pass `resolved` only in tests. */
export function displayTimeZone(resolved?: string): string {
  let tz = resolved
  if (tz === undefined) {
    try {
      tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    } catch {
      tz = undefined
    }
  }
  return tz && tz !== 'UTC' && tz !== 'Etc/UTC' ? tz : HOME_TZ
}

/** "3:05:12 PM CDT" — feed rows (events, predictions). */
export function formatClockTime(ms: number | string, tz: string = displayTimeZone()): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(Number(ms) || 0)
}

/** "Sat, Jul 11, 4:00 PM CDT" — scheduled fight dates. */
export function formatEventDate(ms: number | string, tz: string = displayTimeZone()): string {
  const n = Number(ms) || 0
  if (!n) return 'Date TBA'
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(n)
}
