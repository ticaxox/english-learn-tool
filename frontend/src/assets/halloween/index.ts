/**
 * Halloween art set: one entry per asset, each with a day and a night image.
 *
 * Import paths are explicit so Vite resolves every file at build time; a
 * missing or renamed PNG fails the build instead of shipping a broken <img>.
 * See README.md for the naming rule and the groups that must not be sliced.
 */

export type Mode = 'day' | 'night'
export type ThemeMode = Readonly<Record<Mode, string>>

/** Every practice type that has a painted cover: five AI exercise types plus the three memory modules. */
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
import conversationDay from './book/book-conversation-day.png'
import conversationNight from './book/book-conversation-night.png'
import settingsCardDay from './card/settings-card-day.png'
import settingsCardNight from './card/settings-card-night.png'

/** Keyed by the product's own type names; `cloze` is the file name for fill-blank. */
export const practiceBooks: PracticeArt = {
  flashcard: { day: flashcardDay, night: flashcardNight },
  choice: { day: choiceDay, night: choiceNight },
  spelling: { day: spellingDay, night: spellingNight },
  fill_blank: { day: fillBlankDay, night: fillBlankNight },
  reading: { day: readingDay, night: readingNight },
  translation: { day: translationDay, night: translationNight },
  writing: { day: writingDay, night: writingNight },
  conversation: { day: conversationDay, night: conversationNight },
}

/** 设置不是一本书：它是一张立起来的卡片，和书站在同一块木板上。 */
export const settingsCard: ThemeMode = { day: settingsCardDay, night: settingsCardNight }

import slabBiscuit from './card/slab-biscuit.png'
import slabStele from './card/slab-stele.png'
import barBiscuit from './card/bar-biscuit.png'
import barBiscuitOn from './card/bar-biscuit-on.png'
import barStele from './card/bar-stele.png'
import barSteleOn from './card/bar-stele-on.png'
import chipBiscuit from './card/chip-biscuit.png'
import chipStele from './card/chip-stele.png'
import sheetBrassDay from './card/sheet-brass-day.png'
import sheetBrassNight from './card/sheet-brass-night.png'
import sheetParchedDay from './card/sheet-parched-day.png'
import sheetParchedNight from './card/sheet-parched-night.png'
import wordbookCoverDay from './card/wordbook-cover-day.png'
import wordbookCoverNight from './card/wordbook-cover-night.png'
import cardFrameDay from './card/card-frame-day.png'
import cardFrameNight from './card/card-frame-night.png'
import cardBack from './card/card-back.png'
import paperCardDay from './card/card-frame-paper-day.png'
import paperCardNight from './card/card-frame-paper-night.png'
import optionPlateDay from './card/option-plate-day.png'
import optionPlateNight from './card/option-plate-night.png'
import optionTokenDay from './card/option-token-day.png'
import optionTokenNight from './card/option-token-night.png'
import letterTileDay from './card/letter-tile-day.png'
import letterTileNight from './card/letter-tile-night.png'

/** The question card. The frame is exactly 2:3; do not stretch it. */
export const questionCard = {
  frame: { day: cardFrameDay, night: cardFrameNight },
  back: cardBack,
} as const

/**
 * The cut-paper card: an olive rule, a hairline inside it, a diamond at each
 * corner and a blank face. 3:2, meant for a 9-slice — the rim lives in the
 * border band, the blank face is what stretches. The memory drills use it, and
 * so does every other question card, so one stock runs through the product.
 */
export const paperCard = { day: paperCardDay, night: paperCardNight } as const

export const drillFrame = {
  choice: { day: paperCardDay, night: paperCardNight },
  spelling: { day: paperCardDay, night: paperCardNight },
} as const

/**
 * The two places a letter goes. The option marker is a round stone token —
 * the choice drill is carved, so its letters sit on a carved disc. The
 * spelling cell is a tile: baked by day, cut by night, like its frame.
 */
export const letterMark = {
  optionToken: { day: optionTokenDay, night: optionTokenNight },
  letterTile: { day: letterTileDay, night: letterTileNight },
  // The option itself: one plate, always the same length, so a two-word
  // choice and a one-word choice line up.
  optionPlate: { day: optionPlateDay, night: optionPlateNight },
} as const

/**
 * The two materials of the app. Day is baked (a biscuit), night is cut (a
 * stele). Every one of these is a 9-slice source: the rim and the chipped edge
 * sit in the border band, the flat middle stretches.
 */
export const material = {
  slab: { day: slabBiscuit, night: slabStele },
  bar: { day: barBiscuit, night: barStele },
  barOn: { day: barBiscuitOn, night: barSteleOn },
  chip: { day: chipBiscuit, night: chipStele },
} as const

/**
 * The stone the questions sit on, day and night.
 *
 * The surface rules read these as CSS variables, so the same class paints a
 * biscuit by day and a stele by night without a second set of rules.
 */
export const runeStone = {
  slab: { day: slabBiscuit, night: slabStele },
  chip: { day: chipBiscuit, night: chipStele },
  chipOn: { day: barBiscuitOn, night: barSteleOn },
} as const

/** The paper the AI practice questions are written on.

    Two stocks, because the exercises are two different acts: the graded card
    (fill-blank, reading, translation, and the reading passage itself) is a
    brass-cornered document — a sheet that was bound and filed; the writing
    exercise is a loose sheet, torn out and written on by hand. The old slot
    names stay: `scroll` is the graded card, `parchment` the passage, and
    `torn` the writing paper. */
export const runePaper = {
  scroll: { day: sheetBrassDay, night: sheetBrassNight },
  parchment: { day: sheetBrassDay, night: sheetBrassNight },
  torn: { day: sheetParchedDay, night: sheetParchedNight },
} as const

/** The question surface for the AI exercise types: one sheet, text lives on it. */
export const parchment: ThemeMode = {
  day: sheetBrassDay,
  night: sheetBrassNight,
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
import bookObjectNight from './card/book-object-night.png'
export const bookObject = { day: bookObjectDay, night: bookObjectNight } as const

/* The trail's stops are jack-o'-lanterns: lit for a stop you cleared, a
 * spirit-green one for the stop you are on, a dark unlit one for a stop out
 * of reach. */
import pumpkinGreen from './char/pumpkin-green.png'
import pumpkinGreenNight from './char/pumpkin-green-night.png'
import pumpkinUnlit from './char/pumpkin-unlit.png'
import pumpkinUnlitNight from './char/pumpkin-unlit-night.png'
import pumpkinMorning from './char/pumpkin-morning.png'
import pumpkinDusk from './char/pumpkin-dusk.png'
import pumpkinBoss from './char/pumpkin-boss.png'
import pumpkinBossNight from './char/pumpkin-boss-night.png'
import pumpkinBranch from './char/pumpkin-branch.png'
import pumpkinBranchNight from './char/pumpkin-branch-night.png'
export const pumpkins = {
  /** A cleared stop: bright by morning, a hot burn after dark. */
  lit: { day: pumpkinMorning, night: pumpkinDusk },
  green: { day: pumpkinGreen, night: pumpkinGreenNight },
  unlit: { day: pumpkinUnlit, night: pumpkinUnlitNight },
  /** The last stop wears a crown; a side path is a quiet one. */
  boss: { day: pumpkinBoss, night: pumpkinBossNight },
  branch: { day: pumpkinBranch, night: pumpkinBranchNight },
} as const

/* The charges painted onto the badges: one picture per family of feats. */
import chargeFlame from './char/charge-flame.png'
import chargeFlameNight from './char/charge-flame-night.png'
import chargeMoon from './char/charge-moon.png'
import chargeMoonNight from './char/charge-moon-night.png'
import chargeBook from './char/charge-book.png'
import chargeBookNight from './char/charge-book-night.png'
import chargeCrown from './char/charge-crown.png'
import chargeCrownNight from './char/charge-crown-night.png'
import chargeSkull from './char/charge-skull.png'
import chargeSkullNight from './char/charge-skull-night.png'
import chargeStar from './char/charge-star.png'
import chargeStarNight from './char/charge-star-night.png'
import chargeOwl from './char/charge-owl.png'
import chargeOwlNight from './char/charge-owl-night.png'
import chargeHourglass from './char/charge-hourglass.png'
import chargeHourglassNight from './char/charge-hourglass-night.png'
import chargeKey from './char/charge-key.png'
import chargeKeyNight from './char/charge-key-night.png'
export const charge = {
  flame: { day: chargeFlame, night: chargeFlameNight },
  moon: { day: chargeMoon, night: chargeMoonNight },
  book: { day: chargeBook, night: chargeBookNight },
  crown: { day: chargeCrown, night: chargeCrownNight },
  skull: { day: chargeSkull, night: chargeSkullNight },
  star: { day: chargeStar, night: chargeStarNight },
  owl: { day: chargeOwl, night: chargeOwlNight },
  hourglass: { day: chargeHourglass, night: chargeHourglassNight },
  key: { day: chargeKey, night: chargeKeyNight },
} as const

/* The week's candles: cream wax and an orange flame by day, violet wax and a
 * teal flame after dark. */
import candleDay from './char/candle-day.png'
import candleNight from './char/candle-night.png'
export const candles = { day: candleDay, night: candleNight } as const
