import "./global.css";

import Mapbox from "@rnmapbox/maps";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { env } from "./src/config/env";
import { MapScreen } from "./src/features/map/MapScreen";

if (!env.mapboxToken && __DEV__) {
  console.warn("EXPO_PUBLIC_MAPBOX_TOKEN is not set; the map will not load. See apps/mobile/.env.example.");
}
Mapbox.setAccessToken(env.mapboxToken);

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 2, refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <MapScreen />
        <StatusBar style="dark" />
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
