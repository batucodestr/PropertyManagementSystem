import { TextAreaField, TextField } from "@/components/shared/pms/form-bits";
import { ErrorBanner, LoadingBlock } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslations } from "@/i18n";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import type { AccessInfo, Property } from "@/lib/pms/types";
import { useEffect, useState } from "react";

/** Wifi / kapı kodu düzenleme. Bu bilgiler sadece misafir mesajlarında kullanılır, public API'de yoktur. */
export function AccessInfoDialog({ property, onOpenChange }: {
  property: Property | null;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("pms.accessInfo");
  return (
    <Dialog open={!!property} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("title")}{property ? ` – ${property.name}` : ""}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        {property && <AccessInfoForm key={property.id} propertyId={property.id} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function AccessInfoForm({ propertyId, onDone }: { propertyId: string; onDone: () => void }) {
  const t = useTranslations("pms.accessInfo");
  const tc = useTranslations("pms.finance.common");
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get<AccessInfo>(`/properties/${propertyId}/access-info/`)
      .then((d) => !cancelled && setInfo(d))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => { cancelled = true; };
  }, [propertyId]);

  const set = (key: keyof AccessInfo) => (value: string) => setInfo((i) => i && { ...i, [key]: value });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!info) return;
    setSaving(true);
    setError(null);
    try {
      await api.put(`/properties/${propertyId}/access-info/`, info);
      onDone();
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (!info) return error ? <ErrorBanner message={error} /> : <LoadingBlock />;
  return (
    <>
      <form id="access-form" onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        {error && <ErrorBanner className="sm:col-span-2" message={error} />}
        <TextField label={t("wifiName")} value={info.wifi_name} onChange={set("wifi_name")} error={errors.wifi_name} />
        <TextField label={t("wifiPassword")} value={info.wifi_password} onChange={set("wifi_password")} error={errors.wifi_password} />
        <TextField label={t("doorCode")} value={info.door_code} onChange={set("door_code")} error={errors.door_code} />
        <div className="hidden sm:block" />
        <TextAreaField className="sm:col-span-2" label={t("instructions")} value={info.check_in_instructions} onChange={set("check_in_instructions")} />
        <TextAreaField className="sm:col-span-2" label={t("houseRules")} value={info.house_rules} onChange={set("house_rules")} />
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
        <Button type="submit" form="access-form" disabled={saving}>{t("save")}</Button>
      </DialogFooter>
    </>
  );
}
