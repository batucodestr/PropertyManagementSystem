import { PageMeta } from "@/components/shared/page-meta";
import { TextField } from "@/components/shared/pms/form-bits";
import {
  EmptyState,
  ErrorBanner,
  FilterSelect,
  LoadingBlock,
  PageHeader,
  Panel,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApiAll } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { ChevronLeftIcon, ChevronRightIcon, PencilIcon, PlusIcon, TrashBinIcon } from "@/icons";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import { formatCurrency, formatDate, formatDateShort, toISODate, todayISO } from "@/lib/pms/format";
import type { Property, RatesResponse, SeasonalRate } from "@/lib/pms/types";
import { cn } from "@/utils";
import { addMonths, endOfMonth, format, startOfMonth } from "date-fns";
import { useCallback, useEffect, useState } from "react";
import { MarkupPanel } from "./markup-panel";
import { RateCalendar, RateLegend } from "./rate-calendar";
import { SeasonFormDialog } from "./season-form";

type Selection = { from: string | null; to: string | null };

export default function RatesPage() {
  const t = useTranslations("pms.rates");
  const properties = useApiAll<Property>("/properties/", { ordering: "name" });
  const [chosenId, setChosenId] = useState("");
  const propertyId = chosenId || properties.data?.[0]?.id || "";
  const property = properties.data?.find((p) => p.id === propertyId);

  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [rates, setRates] = useState<RatesResponse | null>(null);
  const [ratesError, setRatesError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>({ from: null, to: null });
  const [editOpen, setEditOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const seasons = useApiAll<SeasonalRate>("/seasonal-rates/", { property: propertyId, ordering: "start_date" });
  const [seasonOpen, setSeasonOpen] = useState(false);
  const [editingSeason, setEditingSeason] = useState<SeasonalRate | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadRates = useCallback(() => {
    if (!propertyId) return;
    api
      .get<RatesResponse>(`/properties/${propertyId}/rates/`, {
        from: toISODate(month),
        to: toISODate(endOfMonth(month)),
      })
      .then((r) => { setRates(r); setRatesError(null); })
      .catch((e) => setRatesError(errorMessage(e)));
  }, [propertyId, month]);
  useEffect(loadRates, [loadRates]);

  const reloadAll = () => { loadRates(); seasons.reload(); };

  const selectDay = (day: string) => {
    setNotice(null);
    if (!selection.from || selection.to) {
      setSelection({ from: day, to: null });
      return;
    }
    const [from, to] = day < selection.from ? [day, selection.from] : [selection.from, day];
    setSelection({ from, to });
    setEditOpen(true);
  };

  const removeSeason = async (s: SeasonalRate) => {
    if (!window.confirm(t("deleteConfirm", { name: s.name }))) return;
    setActionError(null);
    try {
      await api.delete(`/seasonal-rates/${s.id}/`);
      reloadAll();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  const today = todayISO();
  const propertyOptions = (properties.data ?? []).map((p) => ({ value: p.id, label: p.name }));

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          propertyOptions.length > 0 && (
            <FilterSelect
              label={t("property")}
              value={propertyId}
              onChange={(v) => { setChosenId(v); setSelection({ from: null, to: null }); }}
              options={propertyOptions}
            />
          )
        }
      />

      {properties.error ? (
        <ErrorBanner message={properties.error} onRetry={properties.reload} />
      ) : !properties.data ? (
        <LoadingBlock />
      ) : properties.data.length === 0 ? (
        <Panel><EmptyState title={t("noProperties")} description="" /></Panel>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">
            <Panel
              title={format(month, "MMMM yyyy")}
              description={t("selectHint")}
              action={
                <div className="flex items-center gap-1.5">
                  <Button variant="outline" size="icon-sm" aria-label={t("previousMonth")} onClick={() => setMonth((m) => addMonths(m, -1))}>
                    <ChevronLeftIcon className="size-4 rtl:rotate-180" />
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setMonth(startOfMonth(new Date()))}>{t("today")}</Button>
                  <Button variant="outline" size="icon-sm" aria-label={t("nextMonth")} onClick={() => setMonth((m) => addMonths(m, 1))}>
                    <ChevronRightIcon className="size-4 rtl:rotate-180" />
                  </Button>
                </div>
              }
              bodyClassName="flex flex-col gap-4 p-3 sm:p-5"
            >
              {notice && <p role="status" className="text-sm text-emerald-600">{notice}</p>}
              {ratesError ? (
                <ErrorBanner message={ratesError} onRetry={loadRates} />
              ) : !rates || rates.property !== propertyId ? (
                <LoadingBlock />
              ) : (
                <RateCalendar days={rates.days} selection={selection} onSelect={selectDay} today={today} />
              )}
              <RateLegend />
            </Panel>

            <Panel
              title={t("seasons")}
              description={t("seasonsDescription")}
              action={<Button size="sm" onClick={() => { setEditingSeason(null); setSeasonOpen(true); }}><PlusIcon /> {t("addSeason")}</Button>}
            >
              {actionError && <div className="p-4"><ErrorBanner message={actionError} /></div>}
              {seasons.error ? (
                <div className="p-4"><ErrorBanner message={seasons.error} onRetry={seasons.reload} /></div>
              ) : !seasons.data ? (
                <LoadingBlock />
              ) : seasons.data.length === 0 ? (
                <EmptyState title={t("noSeasons")} description={t("noSeasonsDescription")} />
              ) : (
                <div className="custom-scrollbar overflow-x-auto">
                  <table className="min-w-full">
                    <thead className={theadClass}>
                      <tr>
                        <Th>{t("seasonName")}</Th>
                        <Th>{t("dates")}</Th>
                        <Th>{t("nightlyPrice")}</Th>
                        <Th>{t("weekendPrice")}</Th>
                        <Th>{t("minStayLabel")}</Th>
                        <Th className="text-end" />
                      </tr>
                    </thead>
                    <tbody>
                      {seasons.data.map((s) => (
                        <tr key={s.id} className={trClass}>
                          <td className={cn(tdClass, "font-medium text-gray-900 dark:text-white/90")}>{s.name}</td>
                          <td className={cn(tdClass, "whitespace-nowrap")}>{formatDateShort(s.start_date)} – {formatDate(s.end_date)}</td>
                          <td className={tdClass}>{formatCurrency(s.nightly_price)}</td>
                          <td className={tdClass}>{s.weekend_price ? formatCurrency(s.weekend_price) : "—"}</td>
                          <td className={tdClass}>{s.min_stay ?? "—"}</td>
                          <td className={cn(tdClass, "text-end")}>
                            <div className="inline-flex gap-1">
                              <Button variant="ghost" size="icon-xs" aria-label={`${t("editSeason")} ${s.name}`} onClick={() => { setEditingSeason(s); setSeasonOpen(true); }}>
                                <PencilIcon className="size-4" />
                              </Button>
                              <Button variant="ghost" size="icon-xs" aria-label={`${t("delete")} ${s.name}`} onClick={() => removeSeason(s)}>
                                <TrashBinIcon className="size-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>

          {property && <MarkupPanel key={property.id} propertyId={property.id} basePrice={Number(property.base_price)} />}
        </div>
      )}

      {propertyId && (
        <>
          <RangeEditDialog
            open={editOpen}
            onOpenChange={(o) => { setEditOpen(o); if (!o) setSelection({ from: null, to: null }); }}
            propertyId={propertyId}
            selection={selection}
            onSaved={() => { setNotice(t("saved")); loadRates(); }}
          />
          <SeasonFormDialog
            open={seasonOpen}
            onOpenChange={setSeasonOpen}
            propertyId={propertyId}
            season={editingSeason}
            onSaved={reloadAll}
          />
        </>
      )}
    </>
  );
}

function RangeEditDialog({
  open,
  onOpenChange,
  propertyId,
  selection,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  propertyId: string;
  selection: Selection;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.rates");
  const from = selection.from ?? "";
  const to = selection.to ?? from;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {from === to ? t("editDay", { date: from && formatDate(from) }) : t("editRange", { from: from && formatDateShort(from), to: to && formatDate(to) })}
          </DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        {open && from && (
          <RangeEditForm
            propertyId={propertyId}
            from={from}
            to={to}
            onCancel={() => onOpenChange(false)}
            onSaved={() => { onSaved(); onOpenChange(false); }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function RangeEditForm({
  propertyId,
  from,
  to,
  onCancel,
  onSaved,
}: {
  propertyId: string;
  from: string;
  to: string;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.rates");
  const [price, setPrice] = useState("");
  const [minStay, setMinStay] = useState("");
  const [closed, setClosed] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const send = async (body: Record<string, unknown>) => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/properties/${propertyId}/rates/bulk/`, { date_from: from, date_to: to, ...body });
      onSaved();
    } catch (e) {
      setErrors(fieldErrors(e));
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const apply = (e: React.FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = { closed };
    if (price !== "") body.price = price;
    if (minStay !== "") body.min_stay = Number(minStay);
    void send(body);
  };

  return (
    <>
      <form id="range-form" onSubmit={apply} className="grid gap-4">
        {error && <ErrorBanner message={error} />}
        <TextField label={t("price")} type="number" placeholder={t("pricePlaceholder")} value={price} onChange={setPrice} error={errors.price} />
        <TextField label={t("minStayLabel")} type="number" placeholder={t("pricePlaceholder")} value={minStay} onChange={setMinStay} error={errors.min_stay} />
        <label className="flex items-center gap-2.5 text-sm text-gray-700 dark:text-gray-300">
          <Checkbox checked={closed} onCheckedChange={(c) => setClosed(c === true)} />
          {t("closeDates")}
        </label>
      </form>
      <DialogFooter className="sm:justify-between">
        <Button variant="outline" disabled={saving} onClick={() => void send({ clear: true })}>{t("clearOverrides")}</Button>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onCancel}>{t("cancel")}</Button>
          <Button type="submit" form="range-form" disabled={saving}>{t("apply")}</Button>
        </div>
      </DialogFooter>
    </>
  );
}
