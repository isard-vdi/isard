import { mutations } from '@/store/mutations';
import { state } from '@/store/state';

describe('MUTATIONS', () => {
  it('changes menu shown state', () => {
    const vuexState = state;
    mutations.TOGGLE_MENU(vuexState, {});

    expect(vuexState.ui.menu.show).toEqual(false);
  });
});
