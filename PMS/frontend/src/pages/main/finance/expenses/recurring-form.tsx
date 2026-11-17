import { SelectField, TextAreaField, TextField } from "@/components/shared/pms/form-bits";
import { ErrorBanner } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslations } from "@/i18n";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import { todayISO } from "@/lib/pms/format";
import type { Property, RecurringExpense } from "@/lib/pms/types";
import { useState } from "react";
import { EXPENSE_CATEGORIES } from "../utils";

export function RecurringFormDialog({
  open,
  item,
  properties,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  item: RecurringExpense | null;
  properties: Property[];
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.finance.expenses");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item ? t("editRecurring") : t("addRecurring")}</DialogTitle>
        </DialogHeader>
        {open && (
          <RecurringForm
            key={item?.id ?? "new"}
            item={item}
            properties={properties}
            onCancel={() => onOpenChange(false)}
            onSaved={() => { onSaved(); onOpenChange(false); }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function RecurringForm({ item, properties, onCancel, onSaved }: {
  item: RecurringExpense | null;
  properties: Property[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.finance.expenses");
  const tc = useTranslations("pms.finance.common");
  const tcat = useTranslations("pms.finance.categories");
  const [property, setProperty] = useState(item?.property ?? properties[0]?.id ?? "");
  const [category, setCategory] = useState<string>(item?.category ?? "dues");
  const [amount, setAmount] = useState(item?.amount ?? "");
  const [day, setDay] = useState(String(item?.day_of_month ?? 1));
  const [start, setStart] = useState(item?.start_date ?? todayISO());
  const [end, setEnd] = useState(item?.end_date ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [active, setActive] = useState(item?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = {
      property, category, amount, description, is_active: active,
      day_of_month: Number(day), start_date: start, end_date: end || null,
    };
    try {
      if (item) await api.patch(`/finance/recurring-expenses/${item.id}/`, body);
      else await api.post("/finance/recurring-expenses/", body);
      onSaved();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      if (!Object.keys(fe).length || fe.non_field_errors) setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <form id="recurring-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <ErrorBanner className="sm:col-span-2" message={error} />}
        <SelectField label={tc("property")} value={property} onChange={setProperty} error={errors.property}
          options={properties.map((p) => ({ value: p.id, label: p.name }))} />
        <SelectField label={tc("category")} value={category} onChange={setCategory} error={errors.category}
          options={EXPENSE_CATEGORIES.map((c) => ({ value: c, label: tcat(c) }))} />
        <TextField label={tc("amount")} type="number" value={amount} onChange={setAmount} error={errors.amount} required />
        <TextField label={t("dayOfMonth")} type="number" value={day} onChange={setDay} error={errors.day_of_month} required />
        <TextField label={t("startDate")} type="date" value={start} onChange={setStart} error={errors.start_date} required />
        <TextField label={t("endDate")} type="date" value={end} onChange={setEnd} error={errors.end_date} />
        <TextAreaField className="sm:col-span-2" label={tc("description")} value={description} onChange={setDescription} rows={2} />
        <label className="flex items-center gap-2.5 text-sm text-gray-700 sm:col-span-2 dark:text-gray-300">
          <Checkbox checked={active} onCheckedChange={(c) => setActive(c === true)} />
          {t("active")}
        </label>
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{tc("cancel")}</Button>
        <Button type="submit" form="recurring-form" disabled={saving}>{tc("save")}</Button>
      </DialogFooter>
    </>
  );
}
