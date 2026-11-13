/**
 * Anchors a popover panel to the field that opens it.
 *
 * A popover starts centred in the viewport, so the panel has to be placed by
 * hand: under the field when there is room, over it when there is not, and
 * never off the side of the window. It lives in the top layer, so no card's
 * overflow can clip it and no sibling's stacking order can bury it.
 *
 * Light dismiss is ours rather than the platform's. `popover="auto"` would
 * close on the very click that the field uses to open it — the click lands
 * outside the panel, the platform closes it, and the handler opens it again in
 * the same turn. Manual popovers leave that decision here.
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'
import type { Ref } from 'vue'

const MARGIN = 10
const GAP = 8

export interface AnchoredPopover {
  /** Bind with `:ref="bindHost"` on the field. */
  bindHost: (el: unknown) => void
  /** Bind with `:ref="bindPanel"` on the panel. */
  bindPanel: (el: unknown) => void
  isOpen: Ref<boolean>
  open: () => void
  close: () => void
  /** True when the node lives inside the panel, which is a DOM child of the
   *  field even though it is painted in the top layer. */
  containsPanel: (node: Node | null) => boolean
}

export function useAnchoredPopover(onEscape?: () => void): AnchoredPopover {
  const hostRef = ref<HTMLElement | null>(null)
  const panelRef = ref<HTMLElement | null>(null)
  const isOpen = ref(false)

  const bindHost = (el: unknown): void => { hostRef.value = (el as HTMLElement | null) ?? null }
  const bindPanel = (el: unknown): void => { panelRef.value = (el as HTMLElement | null) ?? null }

  function isPopoverOpen(panel: HTMLElement): boolean {
    try {
      return panel.matches(':popover-open')
    } catch {
      // Browsers without the Popover API: the panel degrades to an inline
      // element. Only its placement is lost, not the control.
      return false
    }
  }

  function position(): void {
    const host = hostRef.value
    const panel = panelRef.value
    if (!host || !panel) return
    const rect = host.getBoundingClientRect()
    const width = panel.offsetWidth
    const height = panel.offsetHeight

    let left = rect.left
    if (left + width > window.innerWidth - MARGIN) left = window.innerWidth - width - MARGIN
    if (left < MARGIN) left = MARGIN

    let top = rect.bottom + GAP
    if (top + height > window.innerHeight - MARGIN) {
      const above = rect.top - height - GAP
      top = above >= MARGIN ? above : Math.max(MARGIN, window.innerHeight - height - MARGIN)
    }

    panel.style.left = `${Math.round(left)}px`
    panel.style.top = `${Math.round(top)}px`
  }

  function onPointerDown(event: PointerEvent): void {
    const target = event.target as Node | null
    if (target && (hostRef.value?.contains(target) || panelRef.value?.contains(target))) return
    close()
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Escape') return
    event.preventDefault()
    close()
    onEscape?.()
  }

  function onViewportChange(): void {
    position()
  }

  function open(): void {
    if (isOpen.value) return
    isOpen.value = true
    void nextTick(() => {
      const panel = panelRef.value
      if (!panel) return
      if (typeof panel.showPopover === 'function' && !isPopoverOpen(panel)) panel.showPopover()
      position()
      document.addEventListener('pointerdown', onPointerDown, true)
      document.addEventListener('keydown', onKeydown, true)
      window.addEventListener('resize', onViewportChange)
      window.addEventListener('scroll', onViewportChange, true)
    })
  }

  function close(): void {
    if (!isOpen.value) return
    isOpen.value = false
    const panel = panelRef.value
    if (panel && typeof panel.hidePopover === 'function' && isPopoverOpen(panel)) panel.hidePopover()
    document.removeEventListener('pointerdown', onPointerDown, true)
    document.removeEventListener('keydown', onKeydown, true)
    window.removeEventListener('resize', onViewportChange)
    window.removeEventListener('scroll', onViewportChange, true)
  }

  function containsPanel(node: Node | null): boolean {
    return Boolean(node && panelRef.value?.contains(node))
  }

  onBeforeUnmount(close)

  return { bindHost, bindPanel, isOpen, open, close, containsPanel }
}
