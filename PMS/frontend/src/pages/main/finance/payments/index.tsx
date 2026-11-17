import { PageMeta } from "@/components/shared/page-meta";
import { ChannelBadge } from "@/components/shared/pms/badges";
import { TextField } from "@/components/shared/pms/form-bits";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApiAll, useApiList, useDebounce } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { PencilIcon } from "@/icons";
import { api, errorMessage, fieldErrors, type Paginated } from "@/lib/api";
import { formatCurrency, formatDateShort } from "@/lib/pms/format";
import type { Payment, Property } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useState } from "react";

const PAGE_SIZE = 20;

type PaymentList = Paginated<Payment> & { totals: { gross: string; commission: string; net: string; pending_net: string } };

export default function PaymentsPage() {
  const t = useTranslations("pms.finance.payments");
  const tc = useTranslations("pms.finance.common");
  const tch = useTranslations("pms.finance.channels");
  const [search, setSearch] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [source, setSource] = useState("");
  const [payout, setPayout] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Payment | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const debounced = useDebounce(search.trim());

  const properties = useApiAll<Property>("/properties/", { ordering: "name" });
  const list = useApiList<Payment>("/finance/payments/", {
    search: debounced, property: propertyId, source, payout_status: payout, page, page_size: PAGE_SIZE,
  });
  const data = list.data as PaymentList | null;
  const rows = data?.results ?? [];

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setPage(1); };

  const togglePayout = async (p: Payment) => {
    setActionError(null);
    try {
      await api.patch(`/finance/payments/${p.id}/`, { payout_status: p.payout_status === "paid" ? "pending" : "paid" });
      list.reload();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader title={t("title")} description={t("description")} />

      {data && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label={t("totalGross")} value={formatCurrency(data.totals.gross)} />
          <StatCard label={t("totalCommission")} value={formatCurrency(data.totals.commission)} />
          <StatCard label={t("totalNet")} value={formatCurrency(data.totals.net)} />
          <StatCard label={t("totalPending")} value={formatCurrency(data.totals.pending_net)} />
        </div>
      )}
      {actionError && <ErrorBanner className="mb-4" message={actionError} />}

      <Panel>
        <FilterBar>
          <SearchBox value={search} onChange={resetPage(setSearch)} placeholder={t("searchPlaceholder")} />
          <FilterSelect label={tc("property")} value={propertyId} onChange={resetPage(setPropertyId)} allLabel={tc("allProperties")}
            options={(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
          <FilterSelect label={tc("channel")} value={source} onChange={resetPage(setSource)} allLabel={tc("allChannels")}
            options={(["direct", "airbnb", "booking", "other"] as const).map((s) => ({ value: s, label: tch(s) }))} />
          <FilterSelect label={t("payout")} value={payout} onChange={resetPage(setPayout)} allLabel={t("allPayouts")}
            options={[{ value: "pending", label: t("pending") }, { value: "paid", label: t("paid") }]} />
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
                    <Th className="text-end">{t("net")}</Th>
                    <Th>{t("payout")}</Th>
                    <Th className="text-end">{tc("actions")}</Th>
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
                      <td className={cn(tdClass, "text-end font-medium whitespace-nowrap text-gray-900 dark:text-white/90")}>
                        {formatCurrency(p.net_amount, p.currency)}
                      </td>
                      <td className={tdClass}>
                        <Badge variant="light" size="sm" color={p.payout_status === "paid" ? "success" : "warning"} className="[text-shadow:none]!">
                          {p.payout_status === "paid" ? t("paid") : t("pending")}
                        </Badge>
                        {p.payout_date && <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{formatDateShort(p.payout_date)}</div>}
                      </td>
                      <td className={cn(tdClass, "text-end")}>
                        <div className="inline-flex items-center gap-1">
                          <Button variant="outline" size="xs" onClick={() => togglePayout(p)}>
                            {p.payout_status === "paid" ? t("markPending") : t("markPaid")}
                          </Button>
                          <Button variant="ghost" size="icon-xs" aria-label={`${tc("edit")} ${p.guest_name}`} onClick={() => setEditing(p)}>
                            <PencilIcon className="size-4" />
                          </Button>
                        </div>
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

      <PaymentEditDialog payment={editing} onOpenChange={(o) => !o && setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />
    </>
  );
}

function PaymentEditDialog({ payment, onOpenChange, onSaved }: {
  payment: Payment | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.finance.payments");
  return (
    <Dialog open={!!payment} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{payment ? t("editTitle", { guest: payment.guest_name }) : ""}</DialogTitle>
        </DialogHeader>
        {payment && <PaymentEditForm key={payment.id} payment={payment} onCancel={() => onOpenChange(false)} onSaved={onSaved} />}
      </DialogContent>
    </Dialog>
  );
}

function PaymentEditForm({ payment, onCancel, onSaved }: { payment: Payment; onCancel: () => void; onSaved: () => void }) {
  const t = useTranslations("pms.finance.payments");
  const tc = useTranslations("pms.finance.common");
  const [commission, setCommission] = useState(payment.commission_is_estimated ? "" : (payment.channel_commission ?? ""));
  const [taxes, setTaxes] = useState(payment.taxes);
  const [cleaning, setCleaning] = useState(payment.cleaning_fee);
  const [payoutDate, setPayoutDate] = useState(payment.payout_date ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/finance/payments/${payment.id}/`, {
        channel_commission: commission === "" ? null : commission,
        taxes: taxes || "0",
        cleaning_fee: cleaning || "0",
        ...(payoutDate ? { payout_status: "paid", payout_date: payoutDate } : {}),
      });
      onSaved();
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <form id="payment-form" onSubmit={submit} className="grid gap-4">
        {error && <ErrorBanner message={error} />}
        <div>
          <TextField label={t("commission")} type="number" placeholder={payment.channel_commission ?? ""} value={commission} onChange={setCommission} error={errors.channel_commission} />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("commissionHint")}</p>
        </div>
        <TextField label={t("taxes")} type="number" value={taxes} onChange={setTaxes} error={errors.taxes} />
        <TextField label={t("cleaningFee")} type="number" value={cleaning} onChange={setCleaning} error={errors.cleaning_fee} />
        <TextField label={t("payoutDate")} type="date" value={payoutDate} onChange={setPayoutDate} error={errors.payout_date} />
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{tc("cancel")}</Button>
        <Button type="submit" form="payment-form" disabled={saving}>{tc("save")}</Button>
      </DialogFooter>
    </>
  );
}
