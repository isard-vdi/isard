import { mutations } from '@/store/mutations.ts';
import { state } from '@/store/state.ts';

describe('MUTATIONS', () => {
  it('changes menu shown status', () => {
    const vuexState = state;
    mutations.TOGGLE_MENU(vuexState, {});

    expect(vuexState.ui.menu.show).toEqual(false);
  });
});
