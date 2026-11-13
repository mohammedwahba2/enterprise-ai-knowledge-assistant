import type { ReactNode } from "react";
import { OrgsProvider } from "@/lib/orgs";
import { RequireSession } from "@/components/RequireSession";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <RequireSession>
      <OrgsProvider>{children}</OrgsProvider>
    </RequireSession>
  );
}
