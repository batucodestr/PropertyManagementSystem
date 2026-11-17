import { PageMeta } from "@/components/shared/page-meta";
import { ChannelBadge } from "@/components/shared/pms/badges";
import {
  EmptyState,
  ErrorBanner,
  FilterBar,
  FilterSelect,
  LoadingBlock,
  PageHeader,
  Panel,
  SearchBox,
  StatCard,
  TablePager,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { useApiAll, useApiList, useDebounce } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import type { Paginated } from "@/lib/api";
import { formatCurrency, formatDateShort } from "@/lib/pms/format";
import type { Payment, Property } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useState } from "react";

const PAGE_SIZE = 20;

type PaymentList = Paginated<Payment> & { totals: { gross: string; commission: string; net: string } };

/** Rezervasyonlardan otomatik hesaplanan brüt / komisyon / net listesi (salt-okunur). */
export default function PaymentsPage() {
  const t = useTranslations("pms.finance.payments");
  const tc = useTranslations("pms.finance.common");
  const tch = useTranslations("pms.finance.channels");
  const [search, setSearch] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounce(search.trim());

  const properties = useApiAll<Property>("/properties/", { ordering: "name" });
  const list = useApiList<Payment>("/finance/payments/", {
    search: debounced, property: propertyId, source, page, page_size: PAGE_SIZE,
  });
  const data = list.data as PaymentList | null;
  const rows = data?.results ?? [];

  const resetPage = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader title={t("title")} description={t("description")} />

      {data && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label={t("totalGross")} value={formatCurrency(data.totals.gross)} />
          <StatCard label={t("totalCommission")} value={formatCurrency(data.totals.commission)} />
          <StatCard label={t("totalNet")} value={formatCurrency(data.totals.net)} />
        </div>
      )}

      <Panel>
        <FilterBar>
          <SearchBox value={search} onChange={resetPage(setSearch)} placeholder={t("searchPlaceholder")} />
          <FilterSelect label={tc("property")} value={propertyId} onChange={resetPage(setPropertyId)} allLabel={tc("allProperties")}
            options={(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
          <FilterSelect label={tc("channel")} value={source} onChange={resetPage(setSource)} allLabel={tc("allChannels")}
            options={(["direct", "airbnb", "booking", "other"] as const).map((s) => ({ value: s, label: tch(s) }))} />
        </FilterBar>
        {list.error ? (
          <div className="p-4"><ErrorBanner message={list.error} onRetry={list.reload} /></div>
        ) : !data && list.loading ? (
          <LoadingBlock />
        ) : rows.length === 0 ? (
          <EmptyState title={t("empty")} description={t("emptyDescription")} />
        ) : (
          <>
            <div className={cn("custom-scrollbar overflow-x-auto transition-opacity", list.loading && "opacity-60")}>
              <table className="min-w-full">
                <thead className={theadClass}>
                  <tr>
                    <Th>{t("guest")}</Th>
                    <Th>{t("stay")}</Th>
                    <Th>{tc("channel")}</Th>
                    <Th className="text-end">{t("gross")}</Th>
                    <Th className="text-end">{t("commission")}</Th>
                    <Th className="text-end">{t("taxes")}</Th>
                    <Th className="text-end">{t("net")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} className={trClass}>
                      <td className={tdClass}>
                        <div className="font-medium text-gray-900 dark:text-white/90">{p.guest_name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">{p.property_name}</div>
                      </td>
                      <td className={cn(tdClass, "whitespace-nowrap")}>
                        {formatDateShort(p.check_in)} – {formatDateShort(p.check_out)}
                        {p.channel_booking_ref && <div className="text-xs text-gray-500 dark:text-gray-400">{p.channel_booking_ref}</div>}
                      </td>
                      <td className={tdClass}><ChannelBadge source={p.source} /></td>
                      <td className={cn(tdClass, "text-end whitespace-nowrap")}>{formatCurrency(p.total_price, p.currency)}</td>
                      <td className={cn(tdClass, "text-end whitespace-nowrap")}>
                        {formatCurrency(p.channel_commission ?? 0, p.currency)}
                        {p.commission_is_estimated && (
                          <div className="text-xs text-amber-600 dark:text-amber-400" title={t("estimatedHint")}>{tc("estimated")}</div>
                        )}
                      </td>
                      <td className={cn(tdClass, "text-end whitespace-nowrap")}>{formatCurrency(p.taxes, p.currency)}</td>
                      <td className={cn(tdClass, "text-end font-medium whitespace-nowrap text-gray-900 dark:text-white/90")}>
                        {formatCurrency(p.net_amount, p.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <TablePager page={page} pageCount={Math.ceil((data?.count ?? 0) / PAGE_SIZE)} total={data?.count ?? 0} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}
