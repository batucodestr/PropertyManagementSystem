import { PageMeta } from "@/components/shared/page-meta";
import {
  ErrorBanner,
  FilterSelect,
  LoadingBlock,
  PageHeader,
  Panel,
  StatCard,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { useApiAll } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import { formatCurrency, toISODate } from "@/lib/pms/format";
import type { FinanceSummary, Property } from "@/lib/pms/types";
import { cn } from "@/utils";
import { addMonths, endOfMonth, format, startOfMonth } from "date-fns";
import { useEffect, useState } from "react";
import { downloadCsv } from "../utils";
import { ChannelChart } from "./channel-chart";

export default function ReportsPage() {
  const t = useTranslations("pms.finance.reports");
  const tc = useTranslations("pms.finance.common");
  const tch = useTranslations("pms.finance.channels");
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [propertyId, setPropertyId] = useState("");
  const [result, setResult] = useState<{ key: string; data?: FinanceSummary; error?: string } | null>(null);
  const properties = useApiAll<Property>("/properties/", { ordering: "name" });

  const from = toISODate(month);
  const to = toISODate(endOfMonth(month));
  const key = `${from}|${propertyId}`;

  useEffect(() => {
    let cancelled = false;
    api
      .get<FinanceSummary>("/finance/summary/", { from, to, property: propertyId })
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((e) => !cancelled && setResult({ key, error: errorMessage(e) }));
    return () => { cancelled = true; };
  }, [key, from, to, propertyId]);

  const data = result?.data;
  const loading = result?.key !== key;
  const totals = data?.totals;

  const exportCsv = () => {
    if (!data) return;
    const header = ["Property", "Gross", "Commission", "Taxes", "Net", "Nights", "Reservations", "ADR", "Occupancy %"];
    const row = (name: string, f: FinanceSummary["totals"] | FinanceSummary["by_property"][number]) =>
      [name, f.gross, f.commission, f.taxes, f.net, f.nights, f.reservations, f.adr, f.occupancy ?? ""];
    downloadCsv(`finance-${format(month, "yyyy-MM")}.csv`, [
      header,
      ...data.by_property.map((p) => row(p.name, p)),
      row("TOTAL", data.totals),
      [],
      ["Channel", "Gross", "Commission", "Net", "Nights", "Reservations", "ADR"],
      ...data.by_channel.map((c) => [tch(c.source), c.gross, c.commission, c.net, c.nights, c.reservations, c.adr]),
    ]);
  };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={<Button variant="outline" disabled={!data} onClick={exportCsv}><DownloadIcon className="size-4" /> {t("exportCsv")}</Button>}
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="icon-sm" aria-label={t("previousMonth")} onClick={() => setMonth((m) => addMonths(m, -1))}>
            <ChevronLeftIcon className="size-4 rtl:rotate-180" />
          </Button>
          <span className="min-w-36 text-center font-medium text-gray-900 dark:text-white/90">{format(month, "MMMM yyyy")}</span>
          <Button variant="outline" size="icon-sm" aria-label={t("nextMonth")} onClick={() => setMonth((m) => addMonths(m, 1))}>
            <ChevronRightIcon className="size-4 rtl:rotate-180" />
          </Button>
        </div>
        <FilterSelect label={tc("property")} value={propertyId} onChange={setPropertyId} allLabel={tc("allProperties")}
          options={(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
      </div>

      {result?.error && !loading ? (
        <ErrorBanner message={result.error} />
      ) : !data || !totals ? (
        <LoadingBlock />
      ) : (
        <div className={cn("flex flex-col gap-6 transition-opacity", loading && "opacity-60")}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label={t("gross")} value={formatCurrency(totals.gross)} />
            <StatCard label={t("commission")} value={formatCurrency(totals.commission)} />
            <StatCard label={t("net")} value={formatCurrency(totals.net)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label={t("occupancy")} value={`${totals.occupancy}%`} hint={t("nightsOf", { nights: totals.nights, available: totals.available_nights })} />
            <StatCard label={t("adr")} value={formatCurrency(totals.adr)} hint={t("adrHint")} />
            <StatCard label={t("revpar")} value={formatCurrency(totals.revpar)} hint={t("revparHint")} />
          </div>

          <div className="grid grid-cols-1 gap-6">
            <Panel title={t("byChannel")} description={t("byChannelDescription")} bodyClassName="px-3 pb-3 pt-2">
              <ChannelChart data={data.by_channel} />
              {/* Tablo görünümü: grafikle aynı veri (erişilebilirlik) */}
              <div className="custom-scrollbar overflow-x-auto">
                <table className="min-w-full">
                  <thead className={theadClass}>
                    <tr>
                      <Th>{tc("channel")}</Th>
                      <Th className="text-end">{t("gross")}</Th>
                      <Th className="text-end">{t("commission")}</Th>
                      <Th className="text-end">{t("net")}</Th>
                      <Th className="text-end">{t("nights")}</Th>
                      <Th className="text-end">{t("adr")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_channel.map((c) => (
                      <tr key={c.source} className={trClass}>
                        <td className={tdClass}>{tch(c.source)}</td>
                        <td className={cn(tdClass, "text-end")}>{formatCurrency(c.gross)}</td>
                        <td className={cn(tdClass, "text-end")}>{formatCurrency(c.commission)}</td>
                        <td className={cn(tdClass, "text-end font-medium text-gray-900 dark:text-white/90")}>{formatCurrency(c.net)}</td>
                        <td className={cn(tdClass, "text-end")}>{c.nights}</td>
                        <td className={cn(tdClass, "text-end")}>{formatCurrency(c.adr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

          </div>

          <Panel title={t("byProperty")}>
            <div className="custom-scrollbar overflow-x-auto">
              <table className="min-w-full">
                <thead className={theadClass}>
                  <tr>
                    <Th>{tc("property")}</Th>
                    <Th className="text-end">{t("gross")}</Th>
                    <Th className="text-end">{t("commission")}</Th>
                    <Th className="text-end">{t("net")}</Th>
                    <Th className="text-end">{t("nights")}</Th>
                    <Th className="text-end">{t("occupancy")}</Th>
                    <Th className="text-end">{t("adr")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_property.map((p) => (
                    <tr key={p.property} className={trClass}>
                      <td className={cn(tdClass, "font-medium text-gray-900 dark:text-white/90")}>{p.name}</td>
                      <td className={cn(tdClass, "text-end")}>{formatCurrency(p.gross)}</td>
                      <td className={cn(tdClass, "text-end")}>{formatCurrency(p.commission)}</td>
                      <td className={cn(tdClass, "text-end font-medium text-gray-900 dark:text-white/90")}>{formatCurrency(p.net)}</td>
                      <td className={cn(tdClass, "text-end")}>{p.nights}</td>
                      <td className={cn(tdClass, "text-end")}>{p.occupancy ?? "0.00"}%</td>
                      <td className={cn(tdClass, "text-end")}>{formatCurrency(p.adr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
