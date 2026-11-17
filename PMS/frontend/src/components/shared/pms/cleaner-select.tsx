import { SelectField } from "@/components/shared/pms/form-bits";
import { useApiAll } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import type { UserSummary } from "@/lib/pms/types";

/** 'cleaner' grubundaki kullanıcılardan seçim (boş = atanmamış). */
export function CleanerSelect({ label, value, onChange, error, hint }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  hint?: string;
}) {
  const t = useTranslations("pms.ops");
  const { data } = useApiAll<UserSummary>("/accounts/users/", { group: "cleaner" });
  return (
    <div>
      <SelectField label={label} value={value} onChange={onChange} error={error} placeholder={t("unassigned")}
        options={(data ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))} />
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{data && data.length === 0 ? t("noCleaners") : hint}</p>
    </div>
  );
}
