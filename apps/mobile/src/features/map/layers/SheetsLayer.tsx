import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { Z_INDEX } from "../layers";

/**
 * L3 Bottom sheets and modals: pin detail sheet (UI-4.4), review composer,
 * legend (UI-4.2.8), in-app confirm card (LOC-5.4). Backdrop dims only;
 * never a full-screen takeover, so the map stays visible. Empty for now.
 */
export function SheetsLayer({ children }: { children?: ReactNode }) {
  return (
    <View testID="sheets-layer" pointerEvents="box-none" style={styles.container}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: Z_INDEX.sheets,
    elevation: Z_INDEX.sheets,
  },
});
