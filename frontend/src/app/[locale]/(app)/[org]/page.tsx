import { getTranslations, setRequestLocale } from "next-intl/server";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("Home");

  return (
    <>
      <section className="home">
        <h1>{t("title")}</h1>
        <div className="ask-box">
          <input type="text" disabled placeholder={t("askPlaceholder")} aria-label={t("askPlaceholder")} />
        </div>
        <p className="ask-hint">{t("askUnavailable")}</p>
        <div className="empty">
          <h2>{t("emptyTitle")}</h2>
          <p>{t("emptyBody")}</p>
        </div>
      </section>
    </>
  );
}
