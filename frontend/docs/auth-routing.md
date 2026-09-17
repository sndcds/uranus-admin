# Admin route authentication

`/login` is the only public page (`public: true`, `auth` layout). Every other
route, including future routes, requires a backend-validated system-admin
session. Global Nuxt middleware awaits `useAuthStore().checkSession()` before
page rendering. The default layout also gates its entire shell on `isAdmin`,
so a 401 removes the mounted view while the login navigation completes.

The existing `GET /auth/session` endpoint now uses `get_current_admin`: 200
contains only `subject` and `system_admin`, 401 means missing/invalid session,
and 403 means an authenticated identity lacks system-admin permission. Existing
backend middleware already sends `Cache-Control: private, no-store`. Login,
logout, Argon2id, rate limiting, CSRF/origin checks, cookie options, and the
`/api/v1` authorization dependency are unchanged.

The per-app API plugin uses Nitro's request-scoped `event.fetch` during SSR to
forward the incoming cookie to `/api/admin/auth/session`. The proxy validates
and forwards only the configured session cookie. Browser calls use same-origin
credentials. No token enters Pinia, the Nuxt payload, or browser storage.
Pinia hydrates the server's safe session result; hydration does not recheck it.
Concurrent session checks share one private promise.

Login performs the existing credential request and then validates the session.
Redirect targets preserve query and fragment, permit internal absolute paths
only, and reject external URLs, control characters, backslashes and login
loops. An inherited browser fragment is restored after an SSR redirect because
HTTP requests cannot carry fragments. Navigation uses history replacement.
The login form becomes interactive only after hydration.

A single auth plugin handles protected API 401 responses, resets both data
stores (including filters and pending response generations), and redirects to
login with the current path. Page-local graph/statistics/entity state is
unmounted with the shell. The old `admin-access-revision` and
`admin-auth-status` states and page reload subscriptions are removed; the auth
store owns the only session revision. API request generations prevent an old
401 from invalidating a new login. Protected API 403 responses retain the
session and use the view's existing access-denied error UI.

Logout calls the existing endpoint, clears local state even on failure, and
navigates to `/login` without a return target. On server failure, login displays
a safe warning: the browser cannot revoke an HttpOnly server session itself.
A reload can therefore restore a still-valid server session after failed
logout. No success is claimed for server revocation in that case.

Backend development credentials remain development-only. There is no injected
credential or automatic frontend development bypass. The old embedded manual
credential/login panels are not mounted in the admin shell. Readiness, CSP and
global `noindex, nofollow` are unchanged.

## Validation

Unit/component tests cover the auth store, middleware, redirects, form,
401/403 handling, cache invalidation, concurrent requests and logout failures.
Playwright tests use real HttpOnly fixture sessions for SSR, with fresh anonymous
contexts for auth cases. They check raw SSR redirects, absence of protected DOM
with a MutationObserver, deep-link restoration, hydration, cookie secrecy,
reload, browser Back after logout, session loss and the existing production CSP.
Run both `pnpm test:e2e` and `TEST_PRODUCTION=1 pnpm test:e2e` after `pnpm build`.
The fixture server is test-only; backend tests exercise real database sessions.

## Screenshots

- [Login desktop](auth-screenshots/login-desktop.png)
- [Login mobile](auth-screenshots/login-mobile.png)
- [Authenticated dashboard](auth-screenshots/authenticated-dashboard.png)
- [Anonymous event deep link](auth-screenshots/anonymous-deep-link.png):
  `/events/20000000-0000-4000-8000-000000000001` redirects to
  `/login?redirect=%2Fevents%2F20000000-0000-4000-8000-000000000001`.
