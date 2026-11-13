import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { RequireSession } from "@/components/RequireSession";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <RequireSession>
      <AppShell>{children}</AppShell>
    </RequireSession>
  );
}
