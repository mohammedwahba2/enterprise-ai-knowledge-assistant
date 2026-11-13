import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { OrgGate } from "@/components/OrgGate";

export default function OrgLayout({ children }: { children: ReactNode }) {
  return (
    <OrgGate>
      <AppShell>{children}</AppShell>
    </OrgGate>
  );
}
