import { mount } from '@vue/test-utils';
import IsardInputText from '@/components/shared/forms/IsardInputText.vue';
import MainFormButtons from '@/components/shared/forms/MainFormButtons.vue';

describe('Testing Common components', () => {
  it('checks main button label prop', () => {
    const wrapper = mount(IsardInputText, {
      props: {
        label: 'mylabel'
      }
    });

    expect(wrapper.html().includes('mylabel')).toBe(true);
  });

  it('checks main form buttons visibility hidden', () => {
    const wrapper = mount(MainFormButtons, {
      props: {
        editEnabled: false,
        formChanged: false,
        createMode: false
      }
    });

    expect(wrapper.find('[data-testid="buttEdit"]').exists()).toBe(true);
  });

  it('checks main form buttons edit visibility', () => {
    const wrapper = mount(MainFormButtons, {
      props: {
        editEnabled: true,
        formChanged: false,
        createMode: false
      }
    });

    expect(wrapper.find('[class="buttEdit"]').exists()).toBe(false);
  });
});
