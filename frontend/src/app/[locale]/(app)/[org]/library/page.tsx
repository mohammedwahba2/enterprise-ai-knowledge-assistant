import { setRequestLocale } from "next-intl/server";
import { LibraryPage } from "@/components/library/LibraryPage";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <LibraryPage />;
}
