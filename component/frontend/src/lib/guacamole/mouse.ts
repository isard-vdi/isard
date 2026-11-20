import Guacamole from '@isard/guacamole-common-js'
import type { Mouse } from 'guacamole-common-js'

type MouseStateHandler = (state: Mouse.State) => void

type LegacyWheelEvent = WheelEvent & { wheelDeltaY?: number; wheelDelta?: number }

function cancelEvent(e: Event) {
  e.stopPropagation()
  e.preventDefault()
  e.returnValue = false
}

let css3CursorSupported: boolean | undefined

function isCss3CursorSupported(): boolean {
  if (css3CursorSupported !== undefined) return css3CursorSupported
  const div = document.createElement('div')
  if (!('cursor' in div.style)) return (css3CursorSupported = false)
  try {
    div.style.cursor =
      'url(data:image/png;base64,' +
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB' +
      'AQMAAAAl21bKAAAAA1BMVEX///+nxBvI' +
      'AAAACklEQVQI12NgAAAAAgAB4iG8MwAA' +
      'AABJRU5ErkJggg==) 0 0, auto'
  } catch {
    return (css3CursorSupported = false)
  }
  return (css3CursorSupported = /\burl\([^()]*\)\s+0\s+0\b/.test(div.style.cursor || ''))
}

export class GuacMouse {
  touchMouseThreshold = 3
  scrollThreshold = 53
  PIXELS_PER_LINE = 18
  PIXELS_PER_PAGE = this.PIXELS_PER_LINE * 16

  currentState: Mouse.State = new Guacamole.Mouse.State(0, 0, false, false, false, false, false)

  onmousedown: MouseStateHandler | null = null
  onmouseup: MouseStateHandler | null = null
  onmousemove: MouseStateHandler | null = null
  onmouseout: (() => void) | null = null

  private readonly element: HTMLElement
  private ignoreMouse = 0
  private scrollDelta = 0

  constructor(element: HTMLElement) {
    this.element = element

    element.addEventListener('contextmenu', cancelEvent, false)
    element.addEventListener('mousemove', this.handleMouseMove, false)
    element.addEventListener('mousedown', this.handleMouseDown, false)
    element.addEventListener('mouseup', this.handleMouseUp, false)
    element.addEventListener('mouseout', this.handleMouseOut, false)
    element.addEventListener('selectstart', cancelEvent, false)

    element.addEventListener('touchmove', this.ignorePendingMouseEvents, false)
    element.addEventListener('touchstart', this.ignorePendingMouseEvents, false)
    element.addEventListener('touchend', this.ignorePendingMouseEvents, false)

    element.addEventListener('DOMMouseScroll', this.handleWheel, false)
    element.addEventListener('mousewheel', this.handleWheel, false)
    element.addEventListener('wheel', this.handleWheel, false)
  }

  setCursor(canvas: HTMLCanvasElement, x: number, y: number): boolean {
    if (!isCss3CursorSupported()) return false
    this.element.style.cursor = `url(${canvas.toDataURL('image/png')}) ${x} ${y}, auto`
    return true
  }

  private ignorePendingMouseEvents = () => {
    this.ignoreMouse = this.touchMouseThreshold
  }

  private handleMouseMove = (e: MouseEvent) => {
    if (this.ignoreMouse) {
      this.ignoreMouse--
      return
    }
    this.currentState.fromClientPosition(this.element, e.clientX, e.clientY)
    this.onmousemove?.(this.currentState)
  }

  private handleMouseDown = (e: MouseEvent) => {
    cancelEvent(e)
    if (this.ignoreMouse) return
    this.setButton(e.button, true)
    this.onmousedown?.(this.currentState)
  }

  private handleMouseUp = (e: MouseEvent) => {
    cancelEvent(e)
    if (this.ignoreMouse) return
    this.setButton(e.button, false)
    this.onmouseup?.(this.currentState)
  }

  private handleMouseOut = (e: MouseEvent) => {
    let target = e.relatedTarget as Node | null
    while (target) {
      if (target === this.element) return
      target = target.parentNode
    }

    cancelEvent(e)

    const state = this.currentState
    if (state.left || state.middle || state.right) {
      state.left = false
      state.middle = false
      state.right = false
      this.onmouseup?.(state)
    }

    this.onmouseout?.()
  }

  private handleWheel = (event: Event) => {
    const e = event as LegacyWheelEvent
    let delta = e.deltaY || -(e.wheelDeltaY ?? 0) || -(e.wheelDelta ?? 0)

    if (delta) {
      if (e.deltaMode === 1) {
        delta = e.deltaY * this.PIXELS_PER_LINE
      } else if (e.deltaMode === 2) {
        delta = e.deltaY * this.PIXELS_PER_PAGE
      }
    } else {
      delta = e.detail * this.PIXELS_PER_LINE
    }

    this.scrollDelta += delta

    if (this.scrollDelta <= -this.scrollThreshold) {
      do {
        this.click('up')
        this.scrollDelta += this.scrollThreshold
      } while (this.scrollDelta <= -this.scrollThreshold)
      this.scrollDelta = 0
    }

    if (this.scrollDelta >= this.scrollThreshold) {
      do {
        this.click('down')
        this.scrollDelta -= this.scrollThreshold
      } while (this.scrollDelta >= this.scrollThreshold)
      this.scrollDelta = 0
    }

    cancelEvent(e)
  }

  private click(button: 'up' | 'down') {
    if (this.onmousedown) {
      this.currentState[button] = true
      this.onmousedown(this.currentState)
    }
    if (this.onmouseup) {
      this.currentState[button] = false
      this.onmouseup(this.currentState)
    }
  }

  private setButton(button: number, pressed: boolean) {
    switch (button) {
      case 0:
        this.currentState.left = pressed
        break
      case 1:
        this.currentState.middle = pressed
        break
      case 2:
        this.currentState.right = pressed
        break
    }
  }
}
