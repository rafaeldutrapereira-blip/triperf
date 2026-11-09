# Pipeline de tiendas (TIENDAS-BUILD, BUILD 370)

Estado: pipeline y activos listos; **nada se ha enviado a ninguna tienda**.

## Identificadores
- appId / applicationId / bundle id: `com.labx.athlete` (ya registrado en el repo desde Sprint 55; se conserva).
- Nombre visible: **LabX**.
- Versión empaquetada = BUILD vigente (`sw.js` `BUILD_VERSION`): Android `versionCode = BUILD`,
  `versionName = 1.0.<BUILD>`; iOS `CURRENT_PROJECT_VERSION = BUILD`, `MARKETING_VERSION = 1.0.<BUILD>`.
  El CI lee el BUILD de `sw.js` y lo pasa por `LABX_BUILD`. **Al subir el BUILD, alinear
  `ios/App/App.xcodeproj/project.pbxproj` (2 sitios por clave) y el default de `android/app/build.gradle`.**

## Android
- Firma solo por variables de entorno (`LABX_KEYSTORE_PATH`, `LABX_KEYSTORE_PASSWORD`, `LABX_KEY_ALIAS`,
  `LABX_KEY_PASSWORD`); sin ellas `bundleRelease` produce un AAB sin firmar.
- Keystore: `python scripts/gen_android_keystore.py C:\Users\rafae\labx-overnight\keystore`
  (PKCS12, RSA 4096, 30 años; genera `labx-release.p12` + `keystore.local.env`). Nunca dentro del repo.
  **Hacer copia de seguridad del .p12 y del .env fuera de la PC** (si se pierde, no se puede actualizar la app).
  Con Play App Signing, este keystore es la *llave de subida*.
- Build local: `python scripts/build_www.py` → `node node_modules/@capacitor/cli/bin/capacitor sync android`
  → cargar el `.env` al entorno → `cd android && gradlew bundleRelease`
  → `android/app/build/outputs/bundle/release/app-release.aab`. Verificar: `jarsigner -verify`.
- CI: `.github/workflows/android-aab.yml` (tag `build-*` o manual). Secrets: `ANDROID_KEYSTORE_BASE64`
  (`base64 -w0 labx-release.p12`), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.

## iOS
- CI: `.github/workflows/ios-build.yml` (macOS, simulador, sin firma). Artefacto `LabX-ios-simulator.zip`.
- Pendiente con cuenta Apple Developer: crear App ID `com.labx.athlete` (capacidad HealthKit), certificado
  de distribución, perfil de aprovisionamiento, clave API de App Store Connect; añadir un job `archive` +
  `xcodebuild -exportArchive` y subir con `xcrun altool`/`fastlane pilot` a TestFlight.
  Textos de privacidad de Apple (nutrition labels) y `NSHealth*UsageDescription` ya existen en Info.plist.

## Activos
`python scripts/build_store_assets.py` regenera todo desde el logo de `icon-512.svg` (Georgia Bold Italic +
Segoe UI Emoji de Windows): íconos Android (legacy/round/adaptive, fondo `#04080F`), splash Android e iOS,
ícono iOS 1024 opaco, y `store-assets/` (ícono Play 512, gráfico de funciones 1024x500). Sin datos personales.

## Cuenta demo para revisores
`scripts/create_review_demo_account.py`: **apagado por defecto** (dry-run); crear exige `--apply` y
`LABX_DEMO_ENABLE=1` + `LABX_DEMO_PASSWORD`. Correr una sola vez en la VM al momento del envío.
Poner las credenciales en las notas de revisión de App Store Connect / Play Console.
