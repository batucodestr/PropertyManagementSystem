import { TextField } from "@/components/shared/pms/form-bits";
import { ErrorBanner, Panel } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { useTranslations } from "@/i18n";
import { api, errorMessage, fieldErrors, type Paginated } from "@/lib/api";
import { formatCurrency } from "@/lib/pms/format";
import type { ChannelListing } from "@/lib/pms/types";
import { useEffect, useState } from "react";
import { COMMISSIONS, suggestedMarkup, withMarkup } from "./utils";

export function MarkupPanel({ propertyId, basePrice }: { propertyId: string; basePrice: number }) {
  const t = useTranslations("pms.rates");
  const [listing, setListing] = useState<ChannelListing | null | undefined>(undefined);
  const [airbnb, setAirbnb] = useState("0");
  const [booking, setBooking] = useState("0");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Bileşen property id ile key'lendiği için her ev için sıfırdan mount olur.
    let cancelled = false;
    api
      .get<Paginated<ChannelListing>>("/integrations/listings/", { property: propertyId })
      .then((data) => {
        if (cancelled) return;
        const l = data.results[0] ?? null;
        setListing(l);
        setAirbnb(l?.airbnb_markup_percent ?? "0");
        setBooking(l?.booking_markup_percent ?? "0");
      })
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => { cancelled = true; };
  }, [propertyId]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!listing) return;
    setSaving(true);
    setError(null);
    setErrors({});
    try {
      const updated = await api.patch<ChannelListing>(`/integrations/listings/${listing.id}/`, {
        airbnb_markup_percent: airbnb || "0",
        booking_markup_percent: booking || "0",
      });
      setListing(updated);
      setSaved(true);
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel title={t("markup")} description={t("markupDescription")} bodyClassName="p-5">
      {error && <ErrorBanner className="mb-4" message={error} />}
      {listing === null ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">{t("markupNotLinked")}</p>
      ) : listing === undefined ? null : (
        <form className="grid gap-4" onSubmit={save} onChange={() => setSaved(false)}>
          {([
            ["airbnb", airbnb, setAirbnb, t("airbnbMarkup"), errors.airbnb_markup_percent],
            ["booking", booking, setBooking, t("bookingMarkup"), errors.booking_markup_percent],
          ] as const).map(([key, value, setter, label, err]) => (
            <div key={key}>
              <TextField label={label} type="number" value={value} onChange={setter} error={err} />
              <p className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                {t("suggested", { value: suggestedMarkup(COMMISSIONS[key]), commission: String(COMMISSIONS[key]) })}
                <button
                  type="button"
                  className="font-medium text-brand-500 hover:underline dark:text-brand-400"
                  onClick={() => { setter(suggestedMarkup(COMMISSIONS[key])); setSaved(false); }}
                >
                  {t("useSuggested")}
                </button>
              </p>
            </div>
          ))}
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t("example", {
              base: formatCurrency(basePrice),
              airbnb: formatCurrency(withMarkup(basePrice, airbnb)),
              booking: formatCurrency(withMarkup(basePrice, booking)),
            })}
          </p>
          <p className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-white/3 dark:text-gray-400">{t("markupMapping")}</p>
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={saving}>{t("saveMarkup")}</Button>
            {saved && <span role="status" className="text-sm text-emerald-600">{t("markupSaved")}</span>}
          </div>
        </form>
      )}
    </Panel>
  );
}
