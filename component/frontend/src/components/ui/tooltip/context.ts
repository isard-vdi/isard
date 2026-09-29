import { inject, provide, ref, type InjectionKey, type Ref } from 'vue'

const TOOLTIP_TITLE_KEY: InjectionKey<Ref<string | undefined>> = Symbol('tooltip-title')
const TOOLTIP_TRIGGER_TITLE_KEY: InjectionKey<Ref<string | undefined>> =
  Symbol('tooltip-trigger-title')

export function provideTooltipTitle() {
  const title = ref<string>()
  provide(TOOLTIP_TITLE_KEY, title)
  return title
}

export function injectTooltipTitle() {
  return inject(TOOLTIP_TITLE_KEY, null)
}

// Re-provided only by the trigger, so other buttons inside the tooltip root don't take it.
export function provideTooltipTriggerTitle() {
  provide(TOOLTIP_TRIGGER_TITLE_KEY, inject(TOOLTIP_TITLE_KEY, ref()))
}

export function injectTooltipTriggerTitle() {
  return inject(TOOLTIP_TRIGGER_TITLE_KEY, null)
}
