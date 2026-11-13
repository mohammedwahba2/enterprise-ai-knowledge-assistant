import { setRequestLocale } from "next-intl/server";
import { CreateWorkspaceForm } from "@/components/CreateWorkspaceForm";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <CreateWorkspaceForm />;
}
