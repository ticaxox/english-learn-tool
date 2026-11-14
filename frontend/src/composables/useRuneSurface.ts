import { computed } from 'vue'
import { runeStone, runePaper, questionCard, drillFrame, forMode } from '../assets/halloween'
import { themeMode } from './useTheme'

/** Which drill is drawing itself: each one sits on its own material. */
export type RuneDrill = 'choice' | 'spelling' | 'question'

/**
 * The stone the questions sit on, as CSS variables.
 *
 * The surface rules in `controls.css` read `--rune-slab` and friends, so the
 * same class paints a biscuit by day and a stele by night. The pictures are
 * two separate drawings, never a filter over one.
 */
export function useRuneSurface(drill: RuneDrill = 'question') {
  const surface = computed(() => {
    const mode = themeMode.value
    const frame =
      drill === 'choice' ? drillFrame.choice
      : drill === 'spelling' ? drillFrame.spelling
      : questionCard.frame
    return {
      '--rune-slab': `url(${forMode(runeStone.slab, mode)})`,
      '--rune-chip': `url(${forMode(runeStone.chip, mode)})`,
      '--rune-chip-on': `url(${forMode(runeStone.chipOn, mode)})`,
      '--rune-slab-url': `url(${forMode(runeStone.slab, mode)})`,
      '--rune-scroll': `url(${forMode(runePaper.scroll, mode)})`,
      '--rune-parchment': `url(${forMode(runePaper.parchment, mode)})`,
      '--rune-torn': `url(${forMode(runePaper.torn, mode)})`,
      // The question card is the drill's own frame: pumpkins in the corners,
      // vines down the sides, blank parchment in the middle to write on. The
      // two memory drills draw on their own material instead of borrowing it.
      '--rune-card': `url(${forMode(frame, mode)})`,
    }
  })

  return { surface }
}
