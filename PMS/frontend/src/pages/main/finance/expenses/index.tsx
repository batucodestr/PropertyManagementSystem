import { PageMeta } from "@/components/shared/page-meta";
import {
  DateFilter,
  EmptyState,
  ErrorBanner,
  FilterBar,
  FilterSelect,
  LoadingBlock,
  PageHeader,
  Panel,
  SearchBox,
  TablePager,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiAll, useApiList, useDebounce } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { PaperClipIcon, PencilIcon, PlusIcon, TrashBinIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/pms/format";
import type { FinancialTransaction, Property, RecurringExpense } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useState } from "react";
import { EXPENSE_CATEGORIES } from "../utils";
import { ExpenseFormDialog } from "./expense-form";
import { RecurringFormDialog } from "./recurring-form";

const PAGE_SIZE = 20;

export default function ExpensesPage() {
  const t = useTranslations("pms.finance.expenses");
  const tc = useTranslations("pms.finance.common");
  const tcat = useTranslations("pms.finance.categories");
  const [search, setSearch] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [category, setCategory] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<FinancialTransaction | null>(null);
  const [recurringOpen, setRecurringOpen] = useState(false);
  const [editingRecurring, setEditingRecurring] = useState<RecurringExpense | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const debounced = useDebounce(search.trim());

  const properties = useApiAll<Property>("/properties/", { ordering: "name" });
  const list = useApiList<FinancialTransaction>("/finance/transactions/", {
    transaction_type: "expense", search: debounced, property: propertyId, category,
    transaction_date__gte: from, transaction_date__lte: to, page, page_size: PAGE_SIZE,
  });
  const recurring = useApiAll<RecurringExpense>("/finance/recurring-expenses/", { property: propertyId });
  const rows = list.data?.results ?? [];
  const total = (list.data as { total?: string } | null)?.total;
  const props = properties.data ?? [];

  const resetPage = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  const remove = async (tx: FinancialTransaction) => {
    if (!window.confirm(t("deleteConfirm"))) return;
    setActionError(null);
    try {
      await api.delete(`/finance/transactions/${tx.id}/`);
      list.reload();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  const removeRecurring = async (r: RecurringExpense) => {
    if (!window.confirm(t("deleteRecurringConfirm"))) return;
    setActionError(null);
    try {
      await api.delete(`/finance/recurring-expenses/${r.id}/`);
      recurring.reload();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={<Button disabled={!props.length} onClick={() => { setEditing(null); setFormOpen(true); }}><PlusIcon /> {t("add")}</Button>}
      />
      {actionError && <ErrorBanner className="mb-4" message={actionError} />}

      <div className="flex flex-col gap-6">
        <Panel>
          <FilterBar>
            <SearchBox value={search} onChange={resetPage(setSearch)} placeholder={t("searchPlaceholder")} />
            <FilterSelect label={tc("property")} value={propertyId} onChange={resetPage(setPropertyId)} allLabel={tc("allProperties")}
              options={props.map((p) => ({ value: p.id, label: p.name }))} />
            <FilterSelect label={tc("category")} value={category} onChange={resetPage(setCategory)} allLabel={t("allCategories")}
              options={EXPENSE_CATEGORIES.map((c) => ({ value: c, label: tcat(c) }))} />
            <DateFilter label={t("from")} value={from} onChange={resetPage(setFrom)} />
            <DateFilter label={t("to")} value={to} onChange={resetPage(setTo)} />
            {total !== undefined && (
              <span className="text-sm font-medium text-gray-700 sm:ms-auto dark:text-gray-300">{t("total", { amount: formatCurrency(total) })}</span>
            )}
          </FilterBar>
          {list.error ? (
            <div className="p-4"><ErrorBanner message={list.error} onRetry={list.reload} /></div>
          ) : !list.data && list.loading ? (
            <LoadingBlock />
          ) : rows.length === 0 ? (
            <EmptyState title={t("empty")} description={t("emptyDescription")} />
          ) : (
            <>
              <div className={cn("custom-scrollbar overflow-x-auto transition-opacity", list.loading && "opacity-60")}>
                <table className="min-w-full">
                  <thead className={theadClass}>
                    <tr>
                      <Th>{tc("date")}</Th>
                      <Th>{tc("property")}</Th>
                      <Th>{tc("category")}</Th>
                      <Th>{tc("description")}</Th>
                      <Th className="text-end">{tc("amount")}</Th>
                      <Th className="text-end">{tc("actions")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((tx) => (
                      <tr key={tx.id} className={trClass}>
                        <td className={cn(tdClass, "whitespace-nowrap")}>{formatDate(tx.transaction_date)}</td>
                        <td className={tdClass}>{tx.property_name}</td>
                        <td className={tdClass}>
                          <span className="inline-flex items-center gap-1.5">
                            {tcat(tx.category)}
                            {tx.is_automatic && (
                              <Badge variant="light" size="sm" color="info" className="[text-shadow:none]!" title={t("autoHint")}>{tc("auto")}</Badge>
                            )}
                          </span>
                        </td>
                        <td className={cn(tdClass, "max-w-xs break-words")}>{tx.description || "—"}</td>
                        <td className={cn(tdClass, "text-end font-medium whitespace-nowrap text-gray-900 dark:text-white/90")}>
                          {formatCurrency(tx.amount, tx.currency)}
                        </td>
                        <td className={cn(tdClass, "text-end")}>
                          <div className="inline-flex gap-1">
                            {tx.receipt && (
                              <a href={tx.receipt} target="_blank" rel="noreferrer" aria-label={t("viewReceipt")}
                                className="inline-flex size-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/5">
                                <PaperClipIcon className="size-4" />
                              </a>
                            )}
                            {!tx.is_automatic && (
                              <>
                                <Button variant="ghost" size="icon-xs" aria-label={tc("edit")} onClick={() => { setEditing(tx); setFormOpen(true); }}>
                                  <PencilIcon className="size-4" />
                                </Button>
                                <Button variant="ghost" size="icon-xs" aria-label={tc("delete")} onClick={() => remove(tx)}>
                                  <TrashBinIcon className="size-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <TablePager page={page} pageCount={Math.ceil((list.data?.count ?? 0) / PAGE_SIZE)} total={list.data?.count ?? 0} pageSize={PAGE_SIZE} onPage={setPage} />
            </>
          )}
        </Panel>

        <Panel
          title={t("recurring")}
          description={t("recurringDescription")}
          action={<Button size="sm" disabled={!props.length} onClick={() => { setEditingRecurring(null); setRecurringOpen(true); }}><PlusIcon /> {t("addRecurring")}</Button>}
        >
          {recurring.error ? (
            <div className="p-4"><ErrorBanner message={recurring.error} onRetry={recurring.reload} /></div>
          ) : !recurring.data ? (
            <LoadingBlock />
          ) : recurring.data.length === 0 ? (
            <EmptyState title={t("noRecurring")} description={t("noRecurringDescription")} />
          ) : (
            <div className="custom-scrollbar overflow-x-auto">
              <table className="min-w-full">
                <thead className={theadClass}>
                  <tr>
                    <Th>{tc("property")}</Th>
                    <Th>{tc("category")}</Th>
                    <Th>{t("dayOfMonth")}</Th>
                    <Th className="text-end">{tc("amount")}</Th>
                    <Th className="text-end">{tc("actions")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {recurring.data.map((r) => (
                    <tr key={r.id} className={trClass}>
                      <td className={tdClass}>{r.property_name}</td>
                      <td className={tdClass}>
                        {tcat(r.category)}
                        {r.description && <div className="text-xs text-gray-500 dark:text-gray-400">{r.description}</div>}
                      </td>
                      <td className={tdClass}>
                        {r.is_active ? t("everyMonth", { day: r.day_of_month }) : (
                          <Badge variant="light" size="sm" color="gray" className="[text-shadow:none]!">{t("paused")}</Badge>
                        )}
                      </td>
                      <td className={cn(tdClass, "text-end whitespace-nowrap")}>{formatCurrency(r.amount, r.currency)}</td>
                      <td className={cn(tdClass, "text-end")}>
                        <div className="inline-flex gap-1">
                          <Button variant="ghost" size="icon-xs" aria-label={tc("edit")} onClick={() => { setEditingRecurring(r); setRecurringOpen(true); }}>
                            <PencilIcon className="size-4" />
                          </Button>
                          <Button variant="ghost" size="icon-xs" aria-label={tc("delete")} onClick={() => removeRecurring(r)}>
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

      <ExpenseFormDialog open={formOpen} expense={editing} properties={props} onOpenChange={setFormOpen} onSaved={list.reload} />
      <RecurringFormDialog open={recurringOpen} item={editingRecurring} properties={props} onOpenChange={setRecurringOpen} onSaved={recurring.reload} />
    </>
  );
}
