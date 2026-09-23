# CAPRE mobile

Bundled Capacitor app for Android and iOS. The interface lives on the device;
Flask, PostgreSQL, and protected manuscripts live on the server. Both platforms
use the same `/api/v1` API and existing accounts. Internet is required for data.

## Included

- Sign-in, token refresh, and server-revoked sign-out.
- Search and paginate the repository; view project details.
- Read approved PDF manuscripts inside the app, without public file URLs.
- View profile and notifications; mark notifications read.
- Offline status, retry, Android back handling, and phone safe-area spacing.

Registration, password recovery, editing profiles, manuscript requests/uploads,
push notifications, and offline document storage remain website/later-release
features. Admin routes are unchanged. Native icons/splash screens are still the
Capacitor defaults and must be replaced before store submission.

## Local browser development

Use Node >=22.13 and the existing Python virtual environment. From the repository
root, apply the migration to your **development** PostgreSQL database and start Flask:

```powershell
.\venv\Scripts\python.exe scripts/migrate.py upgrade
.\venv\Scripts\python.exe run.py
```

In another terminal:

```powershell
cd mobile
npm ci
npm run dev
```

Open the printed localhost address. Vite proxies `/api/v1` to
`http://127.0.0.1:5000`; override `CAPRE_DEV_SERVER` in `mobile/.env` if needed.
Browser preview keeps credentials in memory only, so reloading requires login.
No CORS changes to Flask are needed. Do not expose the Vite development server.

## Connect to a deployed server

Hosting is not configured by this change. Deploy the existing Flask app behind
HTTPS with a production WSGI server, PostgreSQL, persistent private upload
storage, email configuration, and database/file backups. Follow the existing
[production readiness contract](../docs/PRODUCTION_READINESS.md) and run the
repository preflight before release. Database credentials and `SECRET_KEY`
belong only on the server, never in mobile environment variables.

Apply `20260923_mobile_sessions.sql` using `scripts/migrate.py upgrade` before
shipping the API. The existing app starts scheduled cleanup inside each process:
use one application worker until those jobs are moved to a single scheduler.
Preserve `/api/v1` compatibility when updating the server; app binaries update
separately through their stores. Verify `/health/ready` after deployment.

Copy `.env.example` to `.env` and replace `VITE_API_ORIGIN` with the real HTTPS
origin (for example `https://research.your-school.edu`, without a path).
This address is public and bundled into the app. Native HTTP calls use explicit
bearer credentials. Cleartext HTTP, remote page loading, and mixed content are
disabled. A build without a server origin can compile but displays a configuration
error when attempting to connect; it is not a deployable release.

```powershell
npm run sync
npm run android
```

Android Studio needs the SDK/JDK versions required by the pinned Capacitor 8
dependencies. Use an emulator or USB-connected phone for testing. Android
Studio can create a debug APK, then a signed AAB for Google Play. Keep signing
keys outside version control. Native sources are checked in; do not run
`cap add` again.

For iOS, use a Mac with compatible Xcode:

```sh
cd mobile
npm ci
npm run sync
npm run ios
```

Choose the Apple signing team and a registered bundle ID, test on a real iPhone,
and archive for TestFlight. `edu.capre.mobile` is a development identifier;
update the Capacitor config and native Android application ID/Java package and
iOS bundle ID consistently before distribution. Windows can generate/sync the
iOS project, but cannot compile or sign it.

## Authentication and privacy

Access tokens expire in 15 minutes; refresh sessions have an absolute 30-day
lifetime. Refresh rotates both tokens atomically; logout deletes the session.
Only SHA-256 digests are stored in PostgreSQL. The native refresh token is kept
in iOS Keychain/Android Keystore-backed storage, with iCloud synchronization
disabled. Access tokens stay in memory. Password changes, inactive accounts,
lockouts, and role changes are checked against the current database state.
API routes never accept Flask cookie sessions and return `Cache-Control: no-store`.

The reader holds PDFs in memory, renders one page at a time, and releases them
when navigating away. No offline PDF cache is created. Only approved, nonarchived
PDFs are served; API metadata omits private storage paths. Notifications refresh
when opened or when Refresh is tapped; they are not push notifications.

## Verification

```powershell
# Repository root
.\venv\Scripts\python.exe -m pytest tests/test_mobile_api.py tests/test_mobile_ui.py -q
# mobile/
npm test
npm run build
```

Database tests use an isolated temporary PostgreSQL cluster, never the configured
application database. UI tests need Playwright Chromium and installed mobile
dependencies; they use fixture API responses. Before distribution, verify real
server login/refresh/logout, revoked manuscript access, slow/offline networks,
app restart, PDFs, and keyboard/back behavior on both platforms. Add final icons,
privacy disclosures, screenshots, signing, and store review information.

References: [Capacitor setup](https://capacitorjs.com/docs/getting-started/environment-setup),
[secure storage](https://github.com/aparajita/capacitor-secure-storage),
[Apple review requirements](https://developer.apple.com/app-store/review/guidelines/).
