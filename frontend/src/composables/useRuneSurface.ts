import { computed } from 'vue'
import { runeStone, runePaper, forMode } from '../assets/halloween'
import { themeMode } from './useTheme'

/**
 * The stone the questions sit on, as CSS variables.
 *
 * The surface rules in `controls.css` read `--rune-slab` and friends, so the
 * same class paints a biscuit by day and a stele by night. The pictures are
 * two separate drawings, never a filter over one.
 */
export function useRuneSurface() {
  const surface = computed(() => {
    const mode = themeMode.value
    return {
      '--rune-slab': `url(${forMode(runeStone.slab, mode)})`,
      '--rune-chip': `url(${forMode(runeStone.chip, mode)})`,
      '--rune-chip-on': `url(${forMode(runeStone.chipOn, mode)})`,
      '--rune-slab-url': `url(${forMode(runeStone.slab, mode)})`,
      '--rune-scroll': `url(${forMode(runePaper.scroll, mode)})`,
      '--rune-parchment': `url(${forMode(runePaper.parchment, mode)})`,
    }
  })

  return { surface }
}
