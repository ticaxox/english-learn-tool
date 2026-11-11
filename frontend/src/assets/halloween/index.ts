/**
 * Halloween art set: one entry per asset, each with a day and a night image.
 *
 * Import paths are explicit so Vite resolves every file at build time; a
 * missing or renamed PNG fails the build instead of shipping a broken <img>.
 * See README.md for the naming rule and the groups that must not be sliced.
 */

export type Mode = 'day' | 'night'
export type ThemeMode = Readonly<Record<Mode, string>>

/** The seven practice types. Keys match PRACTICE_TYPE_LABELS plus the three memory modules. */
export type PracticeArt = Readonly<Record<string, ThemeMode>>

import flashcardDay from './book/book-flashcard-day.png'
import flashcardNight from './book/book-flashcard-night.png'
import choiceDay from './book/book-choice-day.png'
import choiceNight from './book/book-choice-night.png'
import spellingDay from './book/book-spelling-day.png'
import spellingNight from './book/book-spelling-night.png'
import fillBlankDay from './book/book-cloze-day.png'
import fillBlankNight from './book/book-cloze-night.png'
import readingDay from './book/book-reading-day.png'
import readingNight from './book/book-reading-night.png'
import translationDay from './book/book-translation-day.png'
import translationNight from './book/book-translation-night.png'
import writingDay from './book/book-writing-day.png'
import writingNight from './book/book-writing-night.png'

/** Keyed by the product's own type names; `cloze` is the file name for fill-blank. */
export const practiceBooks: PracticeArt = {
  flashcard: { day: flashcardDay, night: flashcardNight },
  choice: { day: choiceDay, night: choiceNight },
  spelling: { day: spellingDay, night: spellingNight },
  fill_blank: { day: fillBlankDay, night: fillBlankNight },
  reading: { day: readingDay, night: readingNight },
  translation: { day: translationDay, night: translationNight },
  writing: { day: writingDay, night: writingNight },
}

import runeSlab from './card/rune-slab.png'
import runeChip from './card/rune-chip.png'
import runeChipOn from './card/rune-chip-on.png'
import wordbookCoverDay from './card/wordbook-cover-day.png'
import wordbookCoverNight from './card/wordbook-cover-night.png'
import cardFrameDay from './card/card-frame-day.png'
import cardFrameNight from './card/card-frame-night.png'
import cardBack from './card/card-back.png'

/** The question card. The frame is exactly 2:3; do not stretch it. */
export const questionCard = {
  frame: { day: cardFrameDay, night: cardFrameNight },
  back: cardBack,
} as const

/**
 * Carved stone for the fill-blank question. Both are 9-slice sources: the
 * chipped edge and the groove sit in the border band, the flat middle stretches.
 */
export const runeStone = {
  slab: runeSlab,
  chip: runeChip,
  chipOn: runeChipOn,
} as const

/** A wordbook cover with nothing printed on it; the title and badges sit on top. */
export const wordbookCover: ThemeMode = {
  day: wordbookCoverDay,
  night: wordbookCoverNight,
}

import brewingDay from './char/brewing-day.png'
import brewingNight from './char/brewing-night.png'
import emptySearchDay from './char/empty-search-day.png'
import emptySearchNight from './char/empty-search-night.png'
import crumboDay from './char/crumbo-day.png'
import crumboNight from './char/crumbo-night.png'
import emptyDay from './char/empty-day.png'
import emptyNight from './char/empty-night.png'
import resultDay from './char/result-day.png'
import resultNight from './char/result-night.png'

/** Large illustrations: the mascot, the empty state, the practice result hero. */
export const illustration = {
  crumbo: { day: crumboDay, night: crumboNight },
  empty: { day: emptyDay, night: emptyNight },
  result: { day: resultDay, night: resultNight },
  /** Crumbo at the cauldron while a set of questions is being generated. */
  brewing: { day: brewingDay, night: brewingNight },
  /** Crumbo with a magnifier for an empty mistakes list. */
  emptySearch: { day: emptySearchDay, night: emptySearchNight },
} as const

import badgesDay from './icon/badges-day.png'
import badgesNight from './icon/badges-night.png'
import dockDay from './icon/dock-day.png'
import dockNight from './icon/dock-night.png'
import actionsDay from './icon/actions-day.png'
import actionsNight from './icon/actions-night.png'

/**
 * Design sheets, NOT sprite sheets: each is a grid of separate icons with no
 * fixed slice coordinates. Redraw as SVG before wiring them into the UI.
 */
export const iconSheet = {
  badges: { day: badgesDay, night: badgesNight },
  dock: { day: dockDay, night: dockNight },
  actions: { day: actionsDay, night: actionsNight },
} as const

import appIcon from './brand/appicon.png'

/** Opaque, full-bleed; the only asset without a transparent background. */
export const brandIcon = appIcon

/** Pick the image for the active theme. */
export function forMode(set: ThemeMode, mode: Mode): string {
  return set[mode]
}

/* Three-piece frames: the two ends keep their painted detail, the middle is a
 * plain strip that stretches, so a wide surface never distorts an edge. */
import scrollCapLeft from './card/scroll-cap-left.png'
import scrollMiddle from './card/scroll-middle.png'
import scrollCapRight from './card/scroll-cap-right.png'
import slabCapLeft from './card/slab-cap-left.png'
import slabMiddle from './card/slab-middle.png'
import slabCapRight from './card/slab-cap-right.png'
import parchmentCapLeft from './card/parchment-cap-left.png'
import parchmentMiddle from './card/parchment-middle.png'
import parchmentCapRight from './card/parchment-cap-right.png'

export type Frame3Part = { left: string; middle: string; right: string }

/** A scroll with rolled rods at both ends. */
export const scrollFrame: Frame3Part = {
  left: scrollCapLeft,
  middle: scrollMiddle,
  right: scrollCapRight,
}

/** A carved stone slab with chipped ends. */
export const slabFrame: Frame3Part = {
  left: slabCapLeft,
  middle: slabMiddle,
  right: slabCapRight,
}

/** A plain sheet of parchment with torn edges. */
export const parchmentFrame: Frame3Part = {
  left: parchmentCapLeft,
  middle: parchmentMiddle,
  right: parchmentCapRight,
}

/** A closed spellbook as an object: spine, page block and clasp, no backdrop. */
import bookObjectDay from './card/book-object-day.png'
export const bookObject = { day: bookObjectDay, night: bookObjectDay } as const

/* The trail's stop markers: a riveted iron token, and the boss's version. */
import nodePlate from './card/node-plate.png'
import nodePlateBoss from './card/node-plate-boss.png'
export const nodeToken = { plate: nodePlate, boss: nodePlateBoss } as const
