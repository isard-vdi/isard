import Guacamole from '@isard/guacamole-common-js'

const mouse = function (element) {
  /**
   * Reference to this Guacamole.Mouse.
   * @private
   */
  const guacMouse = this

  /**
   * The number of mousemove events to require before re-enabling mouse
   * event handling after receiving a touch event.
   */
  this.touchMouseThreshold = 3

  /**
   * The minimum amount of pixels scrolled required for a single scroll button
   * click.
   */
  this.scrollThreshold = 53

  /**
   * The number of pixels to scroll per line.
   */
  this.PIXELS_PER_LINE = 18

  /**
   * The number of pixels to scroll per page.
   */
  this.PIXELS_PER_PAGE = this.PIXELS_PER_LINE * 16

  /**
   * The current mouse state. The properties of this state are updated when
   * mouse events fire. This state object is also passed in as a parameter to
   * the handler of any mouse events.
   *
   * @type {Guacamole.Mouse.State}
   */
  this.currentState = new Guacamole.Mouse.State(
    0, 0,
    false, false, false, false, false
  )

  /**
   * Fired whenever the user presses a mouse button down over the element
   * associated with this Guacamole.Mouse.
   *
   * @event
   * @param {Guacamole.Mouse.State} state The current mouse state.
   */
  this.onmousedown = null

  /**
   * Fired whenever the user releases a mouse button down over the element
   * associated with this Guacamole.Mouse.
   *
   * @event
   * @param {Guacamole.Mouse.State} state The current mouse state.
   */
  this.onmouseup = null

  /**
   * Fired whenever the user moves the mouse over the element associated with
   * this Guacamole.Mouse.
   *
   * @event
   * @param {Guacamole.Mouse.State} state The current mouse state.
   */
  this.onmousemove = null

  /**
   * Fired whenever the mouse leaves the boundaries of the element associated
   * with this Guacamole.Mouse.
   *
   * @event
   */
  this.onmouseout = null

  /**
   * Counter of mouse events to ignore. This decremented by mousemove, and
   * while non-zero, mouse events will have no effect.
   * @private
   */
  let ignoreMouse = 0

  /**
   * Cumulative scroll delta amount. This value is accumulated through scroll
   * events and results in scroll button clicks if it exceeds a certain
   * threshold.
   *
   * @private
   */
  let scrollDelta = 0

  function cancelEvent (e) {
    e.stopPropagation()
    if (e.preventDefault) e.preventDefault()
    e.returnValue = false
  }

  // Block context menu so right-click gets sent properly
  element.addEventListener('contextmenu', function (e) {
    cancelEvent(e)
  }, false)

  element.addEventListener('mousemove', function (e) {
    // If ignoring events, decrement counter
    if (ignoreMouse) {
      ignoreMouse--
      return
    }

    guacMouse.currentState.fromClientPosition(element, e.clientX, e.clientY)

    if (guacMouse.onmousemove) { guacMouse.onmousemove(guacMouse.currentState) }
  }, false)

  element.addEventListener('mousedown', function (e) {
    cancelEvent(e)

    // Do not handle if ignoring events
    if (ignoreMouse) { return }

    switch (e.button) {
      case 0:
        guacMouse.currentState.left = true
        break
      case 1:
        guacMouse.currentState.middle = true
        break
      case 2:
        guacMouse.currentState.right = true
        break
    }

    if (guacMouse.onmousedown) { guacMouse.onmousedown(guacMouse.currentState) }
  }, false)

  element.addEventListener('mouseup', function (e) {
    cancelEvent(e)

    // Do not handle if ignoring events
    if (ignoreMouse) { return }

    switch (e.button) {
      case 0:
        guacMouse.currentState.left = false
        break
      case 1:
        guacMouse.currentState.middle = false
        break
      case 2:
        guacMouse.currentState.right = false
        break
    }

    if (guacMouse.onmouseup) { guacMouse.onmouseup(guacMouse.currentState) }
  }, false)

  element.addEventListener('mouseout', function (e) {
    // Get parent of the element the mouse pointer is leaving
    if (!e) e = window.event

    // Check that mouseout is due to actually LEAVING the element
    let target = e.relatedTarget || e.toElement
    while (target) {
      if (target === element) { return }
      target = target.parentNode
    }

    cancelEvent(e)

    // Release all buttons
    if (guacMouse.currentState.left ||
          guacMouse.currentState.middle ||
          guacMouse.currentState.right) {
      guacMouse.currentState.left = false
      guacMouse.currentState.middle = false
      guacMouse.currentState.right = false

      if (guacMouse.onmouseup) { guacMouse.onmouseup(guacMouse.currentState) }
    }

    // Fire onmouseout event
    if (guacMouse.onmouseout) { guacMouse.onmouseout() }
  }, false)

  // Override selection on mouse event element.
  element.addEventListener('selectstart', function (e) {
    cancelEvent(e)
  }, false)

  // Ignore all pending mouse events when touch events are the apparent source
  function ignorePendingMouseEvents () { ignoreMouse = guacMouse.touchMouseThreshold }

  element.addEventListener('touchmove', ignorePendingMouseEvents, false)
  element.addEventListener('touchstart', ignorePendingMouseEvents, false)
  element.addEventListener('touchend', ignorePendingMouseEvents, false)

  // Scroll wheel support
  function mousewheelHandler (e) {
    // Determine approximate scroll amount (in pixels)
    let delta = e.deltaY || -e.wheelDeltaY || -e.wheelDelta

    // If successfully retrieved scroll amount, convert to pixels if not
    // already in pixels
    if (delta) {
      // Convert to pixels if delta was lines
      if (e.deltaMode === 1) {
        delta = e.deltaY * guacMouse.PIXELS_PER_LINE
      } else if (e.deltaMode === 2) { // Convert to pixels if delta was pages
        delta = e.deltaY * guacMouse.PIXELS_PER_PAGE
      }
    } else { delta = e.detail * guacMouse.PIXELS_PER_LINE } // Otherwise, assume legacy mousewheel event and line scrolling

    // Update overall delta
    scrollDelta += delta

    // Up
    if (scrollDelta <= -guacMouse.scrollThreshold) {
      // Repeatedly click the up button until insufficient delta remains
      do {
        if (guacMouse.onmousedown) {
          guacMouse.currentState.up = true
          guacMouse.onmousedown(guacMouse.currentState)
        }

        if (guacMouse.onmouseup) {
          guacMouse.currentState.up = false
          guacMouse.onmouseup(guacMouse.currentState)
        }

        scrollDelta += guacMouse.scrollThreshold
      } while (scrollDelta <= -guacMouse.scrollThreshold)

      // Reset delta
      scrollDelta = 0
    }

    // Down
    if (scrollDelta >= guacMouse.scrollThreshold) {
      // Repeatedly click the down button until insufficient delta remains
      do {
        if (guacMouse.onmousedown) {
          guacMouse.currentState.down = true
          guacMouse.onmousedown(guacMouse.currentState)
        }

        if (guacMouse.onmouseup) {
          guacMouse.currentState.down = false
          guacMouse.onmouseup(guacMouse.currentState)
        }

        scrollDelta -= guacMouse.scrollThreshold
      } while (scrollDelta >= guacMouse.scrollThreshold)

      // Reset delta
      scrollDelta = 0
    }

    cancelEvent(e)
  }

  element.addEventListener('DOMMouseScroll', mousewheelHandler, false)
  element.addEventListener('mousewheel', mousewheelHandler, false)
  element.addEventListener('wheel', mousewheelHandler, false)

  /**
     * Whether the browser supports CSS3 cursor styling, including hotspot
     * coordinates.
     *
     * @private
     * @type {Boolean}
     */
  const CSS3_CURSOR_SUPPORTED = (function () {
    const div = document.createElement('div')

    // If no cursor property at all, then no support
    if (!('cursor' in div.style)) { return false }

    try {
      // Apply simple 1x1 PNG
      div.style.cursor = 'url(data:image/png;base64,' +
                           'iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB' +
                           'AQMAAAAl21bKAAAAA1BMVEX///+nxBvI' +
                           'AAAACklEQVQI12NgAAAAAgAB4iG8MwAA' +
                           'AABJRU5ErkJggg==) 0 0, auto'
    } catch (e) {
      return false
    }

    // Verify cursor property is set to URL with hotspot
    return /\burl\([^()]*\)\s+0\s+0\b/.test(div.style.cursor || '')
  })()

  /**
   * Changes the local mouse cursor to the given canvas, having the given
   * hotspot coordinates. This affects styling of the element backing this
   * Guacamole.Mouse only, and may fail depending on browser support for
   * setting the mouse cursor.
   *
   * If setting the local cursor is desired, it is up to the implementation
   * to do something else, such as use the software cursor built into
   * Guacamole.Display, if the local cursor cannot be set.
   *
   * @param {HTMLCanvasElement} canvas The cursor image.
   * @param {Number} x The X-coordinate of the cursor hotspot.
   * @param {Number} y The Y-coordinate of the cursor hotspot.
   * @return {Boolean} true if the cursor was successfully set, false if the
   *                   cursor could not be set for any reason.
   */
  this.setCursor = function (canvas, x, y) {
    // Attempt to set via CSS3 cursor styling
    if (CSS3_CURSOR_SUPPORTED) {
      const dataURL = canvas.toDataURL('image/png')
      element.style.cursor = 'url(' + dataURL + ') ' + x + ' ' + y + ', auto'
      return true
    }

    // Otherwise, setting cursor failed
    return false
  }
}

// attach supporting classes
mouse.State = Guacamole.Mouse.State
mouse.Touchpad = Guacamole.Mouse.Touchpad
mouse.Touchscreen = Guacamole.Mouse.Touchscreen

export default {
  mouse
}
