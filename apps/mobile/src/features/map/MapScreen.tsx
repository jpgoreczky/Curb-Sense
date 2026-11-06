import { StyleSheet, View } from "react-native";

import { BaseMapLayer } from "./layers/BaseMapLayer";
import { DataLayer } from "./layers/DataLayer";
import { FloatingActionsLayer } from "./layers/FloatingActionsLayer";
import { NavigationLayer } from "./layers/NavigationLayer";
import { SheetsLayer } from "./layers/SheetsLayer";
import { useMapStore } from "./store";
import { useMapData } from "./useMapData";

/** UI-4.2.1: the layer stack, L0 -> L3 (see layers.ts). */
export function MapScreen() {
  const { collections } = useMapData();
  const mode = useMapStore((s) => s.mode);

  return (
    <View style={styles.root}>
      <BaseMapLayer>
        <DataLayer data={collections} mapMode={mode} />
      </BaseMapLayer>
      <NavigationLayer />
      <FloatingActionsLayer />
      <SheetsLayer />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
