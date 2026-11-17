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

import flashcardDay from './book/book-flashcard-day.webp'
import flashcardNight from './book/book-flashcard-night.webp'
import choiceDay from './book/book-choice-day.webp'
import choiceNight from './book/book-choice-night.webp'
import spellingDay from './book/book-spelling-day.webp'
import spellingNight from './book/book-spelling-night.webp'
import fillBlankDay from './book/book-cloze-day.webp'
import fillBlankNight from './book/book-cloze-night.webp'
import readingDay from './book/book-reading-day.webp'
import readingNight from './book/book-reading-night.webp'
import translationDay from './book/book-translation-day.webp'
import translationNight from './book/book-translation-night.webp'
import writingDay from './book/book-writing-day.webp'
import writingNight from './book/book-writing-night.webp'
import conversationDay from './book/book-conversation-day.webp'
import conversationNight from './book/book-conversation-night.webp'
import settingsCardDay from './card/settings-card-day.webp'
import settingsCardNight from './card/settings-card-night.webp'

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

import slabBiscuit from './card/slab-biscuit.webp'
import slabStele from './card/slab-stele.webp'
import barBiscuit from './card/bar-biscuit.webp'
import barBiscuitOn from './card/bar-biscuit-on.webp'
import barStele from './card/bar-stele.webp'
import barSteleOn from './card/bar-stele-on.webp'
import chipBiscuit from './card/chip-biscuit.webp'
import chipStele from './card/chip-stele.webp'
import sheetBrassDay from './card/sheet-brass-day.webp'
import sheetBrassNight from './card/sheet-brass-night.webp'
import sheetParchedDay from './card/sheet-parched-day.webp'
import sheetParchedNight from './card/sheet-parched-night.webp'
import wordbookCoverDay from './card/wordbook-cover-day.webp'
import wordbookCoverNight from './card/wordbook-cover-night.webp'
import cardFrameDay from './card/card-frame-day.webp'
import cardFrameNight from './card/card-frame-night.webp'
import cardBack from './card/card-back.webp'
import paperCardDay from './card/card-frame-paper-day.webp'
import paperCardNight from './card/card-frame-paper-night.webp'
import optionPlateDay from './card/option-plate-day.webp'
import optionPlateNight from './card/option-plate-night.webp'
import optionTokenDay from './card/option-token-day.webp'
import optionTokenNight from './card/option-token-night.webp'
import letterTileDay from './card/letter-tile-day.webp'
import letterTileNight from './card/letter-tile-night.webp'

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

import brewingDay from './char/brewing-day.webp'
import brewingNight from './char/brewing-night.webp'
import emptySearchDay from './char/empty-search-day.webp'
import emptySearchNight from './char/empty-search-night.webp'
import hobDay from './char/hob-day.webp'
import hobNight from './char/hob-night.webp'
import emptyDay from './char/empty-day.webp'
import emptyNight from './char/empty-night.webp'
import resultDay from './char/result-day.webp'
import resultNight from './char/result-night.webp'
import welcomeDay from './char/welcome-day.webp'
import welcomeNight from './char/welcome-night.webp'
import notFoundDay from './char/notfound-day.webp'
import notFoundNight from './char/notfound-night.webp'
import libraryDay from './char/library-day.webp'
import libraryNight from './char/library-night.webp'
import celebrateDay from './char/celebrate-day.webp'
import celebrateNight from './char/celebrate-night.webp'
import gnawDay from './char/gnaw-day.webp'
import gnawNight from './char/gnaw-night.webp'
import guideDay from './char/guide-day.webp'
import guideNight from './char/guide-night.webp'
import museDay from './char/muse-day.webp'
import museNight from './char/muse-night.webp'

/**
 * Large illustrations: one per moment, not one repeated everywhere.
 *
 * `hob` is the character mark — the same drawing wherever the creature is
 * standing for the product. Every other slot is a different pose for a
 * different moment, so a result page and an empty shelf never show the same
 * picture.
 */
export const illustration = {
  hob: { day: hobDay, night: hobNight },
  /** Reading, face down over an open book: the empty coach. */
  empty: { day: emptyDay, night: emptyNight },
  /** Arms on hips, pleased with itself: the practice result. */
  result: { day: resultDay, night: resultNight },
  /** Waving hello: the sign-in card. */
  welcome: { day: welcomeDay, night: welcomeNight },
  /** A wink, for an address that does not exist. */
  notFound: { day: notFoundDay, night: notFoundNight },
  /** Hugging a book, for an empty shelf. */
  library: { day: libraryDay, night: libraryNight },
  /** Both arms up with sparkles: level-up and a finished drill. */
  celebrate: { day: celebrateDay, night: celebrateNight },
  /** Chewing its own stem: the small avatar that sits in the HUD. */
  gnaw: { day: gnawDay, night: gnawNight },
  /** Pointing the way ahead: today's greeting and the challenge map. */
  guide: { day: guideDay, night: guideNight },
  /** Hand at the chin: the coach's room, where you think out loud. */
  muse: { day: museDay, night: museNight },
  /** Hob at the cauldron while a set of questions is being generated. */
  brewing: { day: brewingDay, night: brewingNight },
  /** Hob with a magnifier for an empty mistakes list. */
  emptySearch: { day: emptySearchDay, night: emptySearchNight },
} as const

import badgesDay from './icon/badges-day.webp'
import badgesNight from './icon/badges-night.webp'
import dockDay from './icon/dock-day.webp'
import dockNight from './icon/dock-night.webp'
import actionsDay from './icon/actions-day.webp'
import actionsNight from './icon/actions-night.webp'

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
import scrollCapLeft from './card/scroll-cap-left.webp'
import scrollMiddle from './card/scroll-middle.webp'
import scrollCapRight from './card/scroll-cap-right.webp'
import slabCapLeft from './card/slab-cap-left.webp'
import slabMiddle from './card/slab-middle.webp'
import slabCapRight from './card/slab-cap-right.webp'
import parchmentCapLeft from './card/parchment-cap-left.webp'
import parchmentMiddle from './card/parchment-middle.webp'
import parchmentCapRight from './card/parchment-cap-right.webp'

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
import bookObjectDay from './card/book-object-day.webp'
import bookObjectNight from './card/book-object-night.webp'
export const bookObject = { day: bookObjectDay, night: bookObjectNight } as const

/* The trail's stops are jack-o'-lanterns: lit for a stop you cleared, a
 * spirit-green one for the stop you are on, a dark unlit one for a stop out
 * of reach. */
import pumpkinGreen from './char/pumpkin-green.webp'
import pumpkinGreenNight from './char/pumpkin-green-night.webp'
import pumpkinUnlit from './char/pumpkin-unlit.webp'
import pumpkinUnlitNight from './char/pumpkin-unlit-night.webp'
import pumpkinMorning from './char/pumpkin-morning.webp'
import pumpkinDusk from './char/pumpkin-dusk.webp'
import pumpkinBoss from './char/pumpkin-boss.webp'
import pumpkinBossNight from './char/pumpkin-boss-night.webp'
import pumpkinBranch from './char/pumpkin-branch.webp'
import pumpkinBranchNight from './char/pumpkin-branch-night.webp'
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
import chargeFlame from './char/charge-flame.webp'
import chargeFlameNight from './char/charge-flame-night.webp'
import chargeMoon from './char/charge-moon.webp'
import chargeMoonNight from './char/charge-moon-night.webp'
import chargeBook from './char/charge-book.webp'
import chargeBookNight from './char/charge-book-night.webp'
import chargeCrown from './char/charge-crown.webp'
import chargeCrownNight from './char/charge-crown-night.webp'
import chargeSkull from './char/charge-skull.webp'
import chargeSkullNight from './char/charge-skull-night.webp'
import chargeStar from './char/charge-star.webp'
import chargeStarNight from './char/charge-star-night.webp'
import chargeOwl from './char/charge-owl.webp'
import chargeOwlNight from './char/charge-owl-night.webp'
import chargeHourglass from './char/charge-hourglass.webp'
import chargeHourglassNight from './char/charge-hourglass-night.webp'
import chargeKey from './char/charge-key.webp'
import chargeKeyNight from './char/charge-key-night.webp'
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

/* The week's candles: one drawing per burn state, day and night. The lengths
 * still come from the day's XP; these drawings change the wax and flame. */
import candleColdDay from './char/candle-cold-day.webp'
import candleLowDay from './char/candle-low-day.webp'
import candleMidDay from './char/candle-mid-day.webp'
import candleHighDay from './char/candle-high-day.webp'
import candleColdNight from './char/candle-cold-night.webp'
import candleLowNight from './char/candle-low-night.webp'
import candleMidNight from './char/candle-mid-night.webp'
import candleHighNight from './char/candle-high-night.webp'

export type CandleState = 'cold' | 'low' | 'mid' | 'high'

export const candleStates: Readonly<Record<Mode, Readonly<Record<CandleState, string>>>> = {
  day: {
    cold: candleColdDay,
    low: candleLowDay,
    mid: candleMidDay,
    high: candleHighDay,
  },
  night: {
    cold: candleColdNight,
    low: candleLowNight,
    mid: candleMidNight,
    high: candleHighNight,
  },
} as const

/** The mid burn state, for callers that only need one candle. */
export const candles = { day: candleMidDay, night: candleMidNight } as const
