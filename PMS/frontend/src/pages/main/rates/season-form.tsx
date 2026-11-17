import { TextField } from "@/components/shared/pms/form-bits";
import { ErrorBanner } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslations } from "@/i18n";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import type { SeasonalRate } from "@/lib/pms/types";
import { useState } from "react";

type Draft = {
  name: string;
  start_date: string;
  end_date: string;
  nightly_price: string;
  weekend_price: string;
  min_stay: string;
};

function toDraft(s: SeasonalRate | null): Draft {
  return {
    name: s?.name ?? "",
    start_date: s?.start_date ?? "",
    end_date: s?.end_date ?? "",
    nightly_price: s?.nightly_price ?? "",
    weekend_price: s?.weekend_price ?? "",
    min_stay: s?.min_stay ? String(s.min_stay) : "",
  };
}

export function SeasonFormDialog({
  open,
  onOpenChange,
  propertyId,
  season,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  propertyId: string;
  season: SeasonalRate | null;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.rates");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{season ? t("editSeason") : t("addSeason")}</DialogTitle>
        </DialogHeader>
        {open && (
          <SeasonForm
            propertyId={propertyId}
            season={season}
            onCancel={() => onOpenChange(false)}
            onSaved={() => { onSaved(); onOpenChange(false); }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function SeasonForm({
  propertyId,
  season,
  onCancel,
  onSaved,
}: {
  propertyId: string;
  season: SeasonalRate | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.rates");
  const [draft, setDraft] = useState<Draft>(() => toDraft(season));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (key: keyof Draft) => (value: string) => setDraft((d) => ({ ...d, [key]: value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = {
      property: propertyId,
      name: draft.name.trim(),
      start_date: draft.start_date,
      end_date: draft.end_date,
      nightly_price: draft.nightly_price,
      weekend_price: draft.weekend_price === "" ? null : draft.weekend_price,
      min_stay: draft.min_stay === "" ? null : Number(draft.min_stay),
    };
    try {
      if (season) await api.patch(`/seasonal-rates/${season.id}/`, body);
      else await api.post("/seasonal-rates/", body);
      onSaved();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      if (Object.keys(fe).length === 0 || fe.non_field_errors) setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <form id="season-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {formError && <ErrorBanner className="sm:col-span-2" message={formError} />}
        <TextField className="sm:col-span-2" label={t("seasonName")} value={draft.name} onChange={set("name")} error={errors.name} required />
        <TextField label={t("startDate")} type="date" value={draft.start_date} onChange={set("start_date")} error={errors.start_date} required />
        <TextField label={t("endDate")} type="date" value={draft.end_date} onChange={set("end_date")} error={errors.end_date} required />
        <TextField label={t("nightlyPrice")} type="number" value={draft.nightly_price} onChange={set("nightly_price")} error={errors.nightly_price} required />
        <TextField label={t("weekendPrice")} type="number" placeholder={t("optional")} value={draft.weekend_price} onChange={set("weekend_price")} error={errors.weekend_price} />
        <TextField label={t("minStayLabel")} type="number" placeholder={t("optional")} value={draft.min_stay} onChange={set("min_stay")} error={errors.min_stay} />
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{t("cancel")}</Button>
        <Button type="submit" form="season-form" disabled={saving}>{t("save")}</Button>
      </DialogFooter>
    </>
  );
}
