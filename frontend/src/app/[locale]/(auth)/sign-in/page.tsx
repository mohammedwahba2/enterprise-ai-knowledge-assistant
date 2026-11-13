import { setRequestLocale } from "next-intl/server";
import { SignInForm } from "@/components/auth/SignInForm";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<{ next?: string }> };

export default async function SignInPage({ params, searchParams }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { next } = await searchParams;
  return <SignInForm next={next ?? null} />;
}
