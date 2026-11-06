import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "../../../theme/tokens";
import { Z_INDEX } from "../layers";

/**
 * L2 Navigation chrome, top-anchored: search bar (UI-4.2.2), filter chips
 * (UI-4.2.3), driving ETA strip (UI-4.3.4). Empty container for now.
 * box-none lets touches fall through to the map wherever there's no control.
 */
export function NavigationLayer({ children }: { children?: ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <View
      testID="navigation-layer"
      pointerEvents="box-none"
      style={[styles.container, { paddingTop: insets.top + spacing[2] }]}
    >
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
    paddingHorizontal: spacing[4],
    zIndex: Z_INDEX.navigation,
    elevation: Z_INDEX.navigation,
  },
});
