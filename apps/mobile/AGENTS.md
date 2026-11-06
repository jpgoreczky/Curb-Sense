# Expo HAS CHANGED

This app is on Expo SDK 57. Read the exact versioned docs at https://docs.expo.dev/versions/v57.0.0/ before writing any code.

- Needs a development build (`expo-dev-client`); Expo Go can't load native Mapbox.
- Mapbox: `@rnmapbox/maps` config plugin. Public token at runtime via `EXPO_PUBLIC_MAPBOX_TOKEN`; Mapbox SDK v11 downloads need no secret download token.
- Flag native iOS/Android permissions whenever a new Expo package is added.
