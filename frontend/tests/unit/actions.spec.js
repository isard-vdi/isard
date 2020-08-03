import { actions } from '@/store'

jest.mock('axios', () => {
  return {
    get: () => ({ data: { userId: 1 } })
  }
})

describe('getPost', () => {
  it('makes a request and commits the response', async () => {
    const store = { commit: jest.fn() }

    await actions.getPost(store)

    expect(store.commit).toHaveBeenCalledWith('SET_POST', { userId: 1 })
  })
})
