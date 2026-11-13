import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  brandIcon,
  bookObject,
  charge,
  forMode,
  iconSheet,
  illustration,
  material,
  practiceBooks,
  pumpkins,
  questionCard,
} from '../assets/halloween'

const here = dirname(fileURLToPath(import.meta.url))
const assetDir = resolve(here, '../assets/halloween')

/** Vite hands back a hashed URL in a build and a plain path in dev; both name a real file. */
function fileOnDisk(url: string): string {
  const clean = url.split('?')[0]
  const name = clean.slice(clean.lastIndexOf('/') + 1)
  const dir = clean.split('/').slice(-2, -1)[0]
  return resolve(assetDir, dir, name)
}

function pngSize(url: string): { width: number; height: number } {
  const buffer = readFileSync(fileOnDisk(url))
  // PNG signature is 8 bytes, then the IHDR length + type are 8 more, so the
  // width and height sit at offsets 16 and 20.
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) }
}

describe('halloween art set', () => {
  it('covers every practice type with both themes', () => {
    expect(Object.keys(practiceBooks).sort()).toEqual([
      'choice',
      'conversation',
      'fill_blank',
      'flashcard',
      'reading',
      'spelling',
      'translation',
      'writing',
    ])
    for (const [type, set] of Object.entries(practiceBooks)) {
      expect(set.day, `${type} day`).toBeTruthy()
      expect(set.night, `${type} night`).toBeTruthy()
      expect(set.day, `${type} day differs from night`).not.toBe(set.night)
    }
  })

  it('ships a day and a night file for every themed set', () => {
    const themed = { ...practiceBooks, ...illustration, ...iconSheet, ...material, frame: questionCard.frame }
    for (const [name, set] of Object.entries(themed)) {
      expect(forMode(set, 'day'), `${name} day`).not.toBe(forMode(set, 'night'))
    }
    expect(questionCard.back).toBeTruthy()
    expect(brandIcon).toBeTruthy()
  })

  it('gives the trail, the book and the badges a night painting of their own', () => {
    const themed = { ...pumpkins, ...charge, book: bookObject }
    for (const [name, set] of Object.entries(themed)) {
      expect(forMode(set, 'day'), `${name} day`).toBeTruthy()
      expect(forMode(set, 'night'), `${name} night`).toBeTruthy()
      expect(forMode(set, 'day'), `${name} day differs from night`).not.toBe(forMode(set, 'night'))
    }
  })

  it('points every import at a file that exists', () => {
    const themed = { ...practiceBooks, ...illustration, ...iconSheet, ...material, frame: questionCard.frame }
    const urls = [
      ...Object.values(themed).flatMap((set) => [set.day, set.night]),
      questionCard.back,
      brandIcon,
    ]
    const missing = urls.filter((url) => !existsSync(fileOnDisk(url)))
    expect(missing).toEqual([])
  })

  it('paints both halves of a pair on the same canvas', () => {
    // Day and night are two generations of one composition. If they are drawn
    // on canvases of different sizes, switching theme resizes and re-centres
    // the picture - the bug this test exists to stop. Sizes below are the
    // shipped canvas for each set; content inside it may differ.
    const themed = { ...practiceBooks, ...illustration }
    const mismatched = Object.entries(themed)
      .map(([name, set]) => ({
        name,
        day: pngSize(set.day),
        night: pngSize(set.night),
      }))
      .filter(({ day, night }) => day.width !== night.width || day.height !== night.height)
      .map(({ name, day, night }) => `${name}: ${day.width}x${day.height} vs ${night.width}x${night.height}`)
    expect(mismatched).toEqual([])
  })

  it('points every night painting at a file that exists', () => {
    const themed = { ...pumpkins, ...charge, book: bookObject }
    const urls = Object.values(themed).map((set) => set.night)
    const missing = urls.filter((url) => !existsSync(fileOnDisk(url)))
    expect(missing).toEqual([])
  })
})
