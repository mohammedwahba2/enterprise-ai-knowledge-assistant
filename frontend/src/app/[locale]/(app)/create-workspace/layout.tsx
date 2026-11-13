import type { ReactNode } from "react";
import { AuthLayoutShell } from "@/components/auth/AuthLayoutShell";

export default function CreateWorkspaceLayout({ children }: { children: ReactNode }) {
  return <AuthLayoutShell>{children}</AuthLayoutShell>;
}
