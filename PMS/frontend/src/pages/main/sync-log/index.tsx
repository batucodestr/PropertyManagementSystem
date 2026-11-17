import { PageMeta } from "@/components/shared/page-meta";
import {
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
import { useApiList, useDebounce } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { RegenerateIcon } from "@/icons";
import { formatDateTime } from "@/lib/pms/format";
import type { SyncLog } from "@/lib/pms/types";
import { cn } from "@/utils";
import { Fragment, useState } from "react";

const PAGE_SIZE = 25;

export default function SyncLogPage() {
  const t = useTranslations("pms.syncLog");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const debounced = useDebounce(search.trim());

  const list = useApiList<SyncLog>("/integrations/sync-logs/", {
    status,
    search: debounced,
    page,
    page_size: PAGE_SIZE,
  });
  const rows = list.data?.results ?? [];
  const total = list.data?.count ?? 0;

  const statusOptions = [
    { value: "success", label: t("success") },
    { value: "error", label: t("error") },
  ];

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={<Button variant="outline" onClick={list.reload}><RegenerateIcon className="size-4" /> {t("refresh")}</Button>}
      />
      <Panel>
        <FilterBar>
          <SearchBox value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder={t("searchPlaceholder")} />
          <FilterSelect
            label={t("status")}
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); }}
            options={statusOptions}
            allLabel={t("allStatuses")}
          />
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
                    <Th>{t("time")}</Th>
                    <Th>{t("action")}</Th>
                    <Th>{t("status")}</Th>
                    <Th>{t("message")}</Th>
                    <Th className="text-end">{t("details")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((log) => (
                    <Fragment key={log.id}>
                      <tr className={trClass}>
                        <td className={cn(tdClass, "whitespace-nowrap")}>{formatDateTime(log.created_at)}</td>
                        <td className={cn(tdClass, "font-mono text-xs whitespace-nowrap")}>{log.action}</td>
                        <td className={tdClass}>
                          <Badge variant="light" size="sm" color={log.status === "error" ? "error" : "success"} className="[text-shadow:none]!">
                            {log.status === "error" ? t("error") : t("success")}
                          </Badge>
                        </td>
                        <td className={cn(tdClass, "max-w-md break-words")}>{log.message}</td>
                        <td className={cn(tdClass, "text-end")}>
                          {Object.keys(log.details ?? {}).length > 0 && (
                            <Button variant="ghost" size="xs" onClick={() => setOpen(open === log.id ? null : log.id)}>
                              {open === log.id ? t("hide") : t("show")}
                            </Button>
                          )}
                        </td>
                      </tr>
                      {open === log.id && (
                        <tr className="border-t border-gray-100 dark:border-gray-800">
                          <td colSpan={5} className="bg-gray-50 px-4 py-3 dark:bg-white/3">
                            <pre className="custom-scrollbar overflow-x-auto text-xs text-gray-700 dark:text-gray-300">
                              {JSON.stringify(log.details, null, 2)}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <TablePager page={page} pageCount={Math.ceil(total / PAGE_SIZE)} total={total} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}
