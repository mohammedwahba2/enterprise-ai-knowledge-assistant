import { setRequestLocale } from "next-intl/server";
import { ResetForm } from "@/components/auth/ResetForm";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ResetForm />;
}
