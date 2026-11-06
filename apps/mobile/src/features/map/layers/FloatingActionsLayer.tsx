import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "../../../theme/tokens";
import { Z_INDEX } from "../layers";

/**
 * L2 Floating actions, bottom-right stack: recenter + add-parking FABs
 * (UI-4.2.7); in driving mode a single >= 60 dp voice FAB (UI-4.3.5).
 * Empty container for now.
 */
export function FloatingActionsLayer({ children }: { children?: ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <View
      testID="floating-actions-layer"
      pointerEvents="box-none"
      style={[styles.container, { bottom: insets.bottom + spacing[4] }]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    right: spacing[4],
    alignItems: "flex-end",
    gap: spacing[3],
    zIndex: Z_INDEX.floatingActions,
    elevation: Z_INDEX.floatingActions,
  },
});
