import { describe, it, expect } from 'vitest'
import { displayTimeZone, formatClockTime, formatEventDate } from '../../lib/time'

describe('displayTimeZone', () => {
  it('keeps a real viewer timezone', () => {
    expect(displayTimeZone('Europe/Paris')).toBe('Europe/Paris')
    expect(displayTimeZone('America/New_York')).toBe('America/New_York')
  })
  it('falls back to Chicago when the browser claims bare UTC (privacy modes)', () => {
    expect(displayTimeZone('UTC')).toBe('America/Chicago')
    expect(displayTimeZone('Etc/UTC')).toBe('America/Chicago')
    expect(displayTimeZone('')).toBe('America/Chicago')
  })
  it('always returns something usable', () => {
    expect(displayTimeZone()).toBeTruthy()
  })
})

describe('formatClockTime', () => {
  // 2026-07-11T21:00:00Z = 4:00 PM in Chicago (CDT, UTC-5)
  const ms = Date.UTC(2026, 6, 11, 21, 0, 0)
  it('renders in the given timezone with a zone label', () => {
    const s = formatClockTime(ms, 'America/Chicago')
    expect(s).toMatch(/4:00:00\sPM/)
    expect(s).toMatch(/CDT/)
  })
  it('coerces wire-string int64 timestamps', () => {
    expect(formatClockTime(String(ms), 'America/Chicago')).toMatch(/4:00:00\sPM/)
  })
})

describe('formatEventDate', () => {
  const ms = Date.UTC(2026, 6, 11, 21, 0, 0)
  it('renders date + time + zone', () => {
    const s = formatEventDate(ms, 'America/Chicago')
    expect(s).toMatch(/Jul/)
    expect(s).toMatch(/11/)
    expect(s).toMatch(/4:00\sPM/)
    expect(s).toMatch(/CDT/)
  })
  it('handles unknown dates', () => {
    expect(formatEventDate(0)).toBe('Date TBA')
    expect(formatEventDate('' as unknown as number)).toBe('Date TBA')
  })
})
