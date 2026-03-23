# NeonTrade AI - Build Instructions

## Desktop (ya generados)

### macOS (.dmg) - LISTO
```
builds/NeonTrade AI-1.0.0-universal.dmg
```
Doble clic para instalar. Arrastra a Applications.

### Windows (.exe) - LISTO
```
builds/NeonTrade AI Setup 1.0.0.exe
```
Enviar al PC Windows y ejecutar el instalador.

## Mobile (requiere cuenta Expo)

### Android (.apk)
```bash
cd frontend
npx eas login          # Login con cuenta Expo (crear en expo.dev)
npx eas build --platform android --profile preview
```
El .apk se descarga desde el link que genera EAS.

### iOS (.ipa)
```bash
npx eas login
npx eas build --platform ios --profile preview
```
Requiere Apple Developer Account ($99/año).

## Regenerar builds

### Rebuild macOS:
```bash
cd frontend
npm run electron:mac
```

### Rebuild Windows:
```bash
cd frontend
npm run electron:win
```

### Rebuild Web:
```bash
cd frontend
npm run build:web
```
