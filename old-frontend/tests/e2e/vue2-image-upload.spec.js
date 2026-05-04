// @ts-check
//
// Regression for round-2 Bug #41 — old-frontend image-upload payload.
//
// Old-frontend's ``DomainImage.vue`` upload widget calls
// ``uploadImageFile`` in ``store/modules/domain.js`` which builds:
//
//   {"image": {"id": "", "type": "user",
//              "file": {"data": "<base64>", "filename": "<name>"}}}
//
// and PUTs it to ``/api/v4/item/{kind}/{id}/edit``. Before commit
// 1ad57bf65 the helper omitted ``id`` and apiv4 422'd with
// ``body.image.id Field required`` because ``DomainImage`` declares
// ``id: str`` as required (Vue 3's ChangeImageModal sends ``id: ""``
// as a sentinel).
//
// The apiv4-side unit test
// (``test_edit_desktop_accepts_image_upload_payload``) pins the
// schema. This e2e adds the live HTTP boundary check: a real PUT
// over TLS to the running stack, with the exact body the Vue 2
// form would send. Catches drift on auth / CORS / rate-limit /
// the deployed apiv4 image vs. what the contract test exercised.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './api-fixture'

test.describe.configure({ mode: 'serial' })

test.describe('Bug #41 — image upload payload accepts empty id sentinel', () => {
  /** @type {string} */
  let desktopId

  test.beforeAll(async ({ baseURL }) => {
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded')
      return
    }

    const ts = Date.now()
    const dsk = await seed.createDesktop(`upload-bug41-${ts}`, tpl.id)
    desktopId = dsk.id
  })

  test.afterAll(async ({ baseURL }) => {
    if (desktopId) {
      try {
        const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
        await cleanup.login()
        await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
      } catch (e) {
        console.warn(`afterAll: deleteDesktop failed: ${e.message}`)
      }
    }
  })

  test('PUT /edit with {image:{id:"",type:"user",file:{data,filename}}} returns 200', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    // 1×1 transparent PNG, base64-encoded. Tiny payload — keeps the
    // request body small and avoids hitting any size limits the
    // staging stack might have.
    const tinyPng =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAeImBZsAAAAASUVORK5CYII='

    const body = {
      image: {
        id: '', // ← the sentinel that Bug #41 was missing.
        type: 'user',
        file: {
          data: tinyPng,
          filename: 'pixel.png'
        }
      }
    }

    // Use the helper's authenticated PUT — same Authorization header
    // shape the Vue 2 form would send.
    const res = await api._authFetch(
      'PUT',
      `/api/v4/item/desktop/${desktopId}/edit`,
      body
    )

    // ``_authFetch`` throws on non-2xx, so reaching this assertion
    // means the PUT was 2xx. The explicit assertion clarifies what
    // the regression check is.
    expect(res, 'edit response body should be present').toBeTruthy()
  })

  test('PUT /edit WITHOUT id (the pre-fix shape) is rejected with 422', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    // This is the exact payload old-frontend used to send before
    // 1ad57bf65 — id missing entirely. Pin the apiv4 schema's
    // requirement so a future loosening (e.g. making id optional)
    // surfaces here, not just in the schema unit test.
    const baseURL = test.info().project.use?.baseURL ?? 'https://localhost'
    const res = await fetch(
      `${baseURL}/api/v4/item/desktop/${desktopId}/edit`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${api.token}`
        },
        body: JSON.stringify({
          image: {
            type: 'user',
            file: {
              data: 'aGVsbG8=', // "hello"
              filename: 'noop.png'
            }
            // ← id omitted intentionally
          }
        })
      }
    )

    expect(
      res.status,
      'apiv4 must reject the pre-fix Vue 2 payload (missing id) with 422; ' +
        `got ${res.status}. If this becomes 200, DomainImage.id has been ` +
        'silently relaxed to optional and the regression contract is gone.'
    ).toBe(422)
  })
})
