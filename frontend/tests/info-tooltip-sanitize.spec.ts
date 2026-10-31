import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import InfoTooltip from '../src/components/common/InfoTooltip.vue'

describe('InfoTooltip', () => {
  it('renders its HTML but strips script from interpolated values', async () => {
    const providerName = '<img src=x onerror="window.__pwned=1">Fidelity<script>window.__pwned=2</script>'
    const wrapper = mount(InfoTooltip, {
      props: { text: `<b>401(k)</b> balance from ${providerName}` },
      attachTo: document.body,
    })
    await wrapper.get('button').trigger('click')
    const tip = document.body.querySelector('.info-tooltip-content')
    expect(tip).not.toBeNull()
    expect(tip!.innerHTML).toContain('<b>401(k)</b>')
    expect(tip!.innerHTML).toContain('Fidelity')
    expect(tip!.innerHTML).not.toContain('onerror')
    expect(tip!.innerHTML).not.toContain('<script')
    wrapper.unmount()
  })
})
