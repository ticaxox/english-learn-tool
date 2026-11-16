import { shallowRef } from 'vue'
import { getWordbookDetail } from '../api/wordbooks'

/**
 * The words of the active wordbook, keyed by their normalised headword, so a
 * highlighted word in a passage can say what it means without asking the
 * server again.
 *
 * One map for the whole app: the reading page fills it when a session opens,
 * and every `SpokenText` on the page reads from it. A word that is not in the
 * book simply has no gloss, and the word stays a word.
 */
export interface WordGloss {
  phonetic: string | null
  meaning: string
}

const glosses = shallowRef<Record<string, WordGloss>>({})
const PAGE_SIZE = 100
const MAX_ENTRIES = 600

export function useWordGlossary() {
  return glosses
}

/** Reads the active wordbook, a page at a time, and keeps only entries that
 *  carry a Chinese definition. Failure is silent: the passage still reads. */
export async function loadWordGlossary(wordbookId: string | null | undefined): Promise<void> {
  if (!wordbookId) {
    glosses.value = {}
    return
  }
  const map: Record<string, WordGloss> = {}
  try {
    for (let offset = 0; offset < MAX_ENTRIES; offset += PAGE_SIZE) {
      const page = await getWordbookDetail(wordbookId, offset, PAGE_SIZE)
      for (const entry of page.entries) {
        const definition =
          entry.definitions.find((item) => item.definition_zh) ?? entry.definitions[0]
        if (!definition?.definition_zh) continue
        map[entry.normalized_headword] = {
          phonetic: entry.phonetic,
          meaning: definition.definition_zh,
        }
      }
      if (page.entries.length < PAGE_SIZE) break
    }
    glosses.value = map
  } catch {
    glosses.value = {}
  }
}
