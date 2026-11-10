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
import runeSlabDay from './card/rune-slab-day.png'
import runeChip from './card/rune-chip.png'
import runeChipOn from './card/rune-chip-on.png'
import runeChipDay from './card/rune-chip-day.png'
import runeChipOnDay from './card/rune-chip-on-day.png'
import scrollDay from './card/scroll-day.png'
import scrollNight from './card/scroll-night.png'
import scrollWideDay from './card/scroll-wide-day.png'
import scrollWideNight from './card/scroll-wide-night.png'
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
  slab: { day: runeSlabDay, night: runeSlab },
  chip: { day: runeChipDay, night: runeChip },
  chipOn: { day: runeChipOnDay, night: runeChipOn },
} as const

/** The question surface for the AI exercise types: one sheet, text lives on it. */
export const parchment: ThemeMode = {
  day: scrollDay,
  night: scrollNight,
}

/** The same sheet on its side, for a passage that runs wide. */
export const parchmentWide: ThemeMode = {
  day: scrollWideDay,
  night: scrollWideNight,
}

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
