import { SelectField, TextAreaField, TextField } from "@/components/shared/pms/form-bits";
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
import { apiFetch, errorMessage, fieldErrors } from "@/lib/api";
import { todayISO } from "@/lib/pms/format";
import type { FinancialTransaction, Property } from "@/lib/pms/types";
import { useState } from "react";
import { EXPENSE_CATEGORIES } from "../utils";

export function ExpenseFormDialog({
  open,
  expense,
  properties,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  expense: FinancialTransaction | null;
  properties: Property[];
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.finance.expenses");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{expense ? t("editTitle") : t("addTitle")}</DialogTitle>
        </DialogHeader>
        {open && (
          <ExpenseForm
            key={expense?.id ?? "new"}
            expense={expense}
            properties={properties}
            onCancel={() => onOpenChange(false)}
            onSaved={() => { onSaved(); onOpenChange(false); }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ExpenseForm({ expense, properties, onCancel, onSaved }: {
  expense: FinancialTransaction | null;
  properties: Property[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.finance.expenses");
  const tc = useTranslations("pms.finance.common");
  const tcat = useTranslations("pms.finance.categories");
  const [property, setProperty] = useState(expense?.property ?? properties[0]?.id ?? "");
  const [category, setCategory] = useState<string>(expense?.category ?? "cleaning");
  const [amount, setAmount] = useState(expense?.amount ?? "");
  const [date, setDate] = useState(expense?.transaction_date ?? todayISO());
  const [description, setDescription] = useState(expense?.description ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const form = new FormData();
    form.append("property", property);
    form.append("transaction_type", "expense");
    form.append("category", category);
    form.append("amount", amount);
    form.append("transaction_date", date);
    form.append("description", description);
    if (file) form.append("receipt", file);
    try {
      if (expense) await apiFetch(`/finance/transactions/${expense.id}/`, { method: "PATCH", body: form });
      else await apiFetch("/finance/transactions/", { method: "POST", body: form });
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
      <form id="expense-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <ErrorBanner className="sm:col-span-2" message={error} />}
        <SelectField label={tc("property")} value={property} onChange={setProperty} error={errors.property}
          options={properties.map((p) => ({ value: p.id, label: p.name }))} />
        <SelectField label={tc("category")} value={category} onChange={setCategory} error={errors.category}
          options={EXPENSE_CATEGORIES.map((c) => ({ value: c, label: tcat(c) }))} />
        <TextField label={tc("amount")} type="number" value={amount} onChange={setAmount} error={errors.amount} required />
        <TextField label={tc("date")} type="date" value={date} onChange={setDate} error={errors.transaction_date} required />
        <TextAreaField className="sm:col-span-2" label={tc("description")} value={description} onChange={setDescription} rows={2} />
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label htmlFor="receipt-input" className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("receipt")}</label>
          <input
            id="receipt-input"
            type="file"
            accept="application/pdf,image/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-gray-700 file:me-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium dark:text-gray-300 dark:file:bg-white/10 dark:file:text-gray-200"
          />
          {expense?.receipt && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              <a href={expense.receipt} target="_blank" rel="noreferrer" className="text-brand-500 hover:underline">{t("viewReceipt")}</a>
              {" · "}{t("replaceReceipt")}
            </p>
          )}
          {errors.receipt && <p className="text-xs text-red-500">{errors.receipt}</p>}
        </div>
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{tc("cancel")}</Button>
        <Button type="submit" form="expense-form" disabled={saving}>{tc("save")}</Button>
      </DialogFooter>
    </>
  );
}
