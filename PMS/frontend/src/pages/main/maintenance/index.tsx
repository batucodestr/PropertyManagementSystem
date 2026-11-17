import { PageMeta } from "@/components/shared/page-meta";
import {
  EmptyState,
  ErrorBanner,
  FilterBar,
  FilterSelect,
  LoadingBlock,
  PageHeader,
  Panel,
  TablePager,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiAll, useApiList } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { CalendarIcon, CameraIcon, PencilIcon, PlusIcon, TrashBinIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import { formatCurrency, formatDateShort } from "@/lib/pms/format";
import type { GeneralTask, Property, TaskPriority } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useState } from "react";
import { IssueFormDialog } from "./issue-form";

const PAGE_SIZE = 20;
const PRIORITY_COLOR: Record<TaskPriority, "gray" | "info" | "warning" | "error"> = {
  low: "gray", normal: "info", high: "warning", critical: "error",
};

export default function MaintenancePage() {
  const t = useTranslations("pms.maintenance");
  const to = useTranslations("pms.ops");
  const tc = useTranslations("pms.finance.common");
  const [propertyId, setPropertyId] = useState("");
  const [priority, setPriority] = useState("");
  const [status, setStatus] = useState("open");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<GeneralTask | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const properties = useApiAll<Property>("/properties/", { ordering: "name" });
  // "open" = pending + in_progress
  const list = useApiList<GeneralTask>("/general-tasks/", {
    task_type: "maintenance",
    property: propertyId,
    priority,
    status: status === "open" ? "" : status,
    status__in: status === "open" ? "pending,in_progress" : "",
    ordering: "status,-priority,due_date",
    page,
    page_size: PAGE_SIZE,
  });
  const rows = list.data?.results ?? [];
  const props = properties.data ?? [];

  const reset = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  const remove = async (task: GeneralTask) => {
    if (!window.confirm(t("deleteConfirm"))) return;
    setActionError(null);
    try {
      await api.delete(`/general-tasks/${task.id}/`);
      list.reload();
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
      <Panel>
        <FilterBar>
          <FilterSelect label={tc("property")} value={propertyId} onChange={reset(setPropertyId)} allLabel={tc("allProperties")}
            options={props.map((p) => ({ value: p.id, label: p.name }))} />
          <FilterSelect label={t("priority")} value={priority} onChange={reset(setPriority)} allLabel={t("allPriorities")}
            options={(["critical", "high", "normal", "low"] as const).map((x) => ({ value: x, label: to(`priority.${x}`) }))} />
          <FilterSelect label={t("status")} value={status} onChange={reset(setStatus)} allLabel={t("allStatuses")}
            options={[
              { value: "open", label: t("openOnly") },
              ...(["pending", "in_progress", "completed"] as const).map((x) => ({ value: x, label: to(`taskStatus.${x}`) })),
            ]} />
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
                    <Th>{t("issue")}</Th>
                    <Th>{tc("property")}</Th>
                    <Th>{t("priority")}</Th>
                    <Th>{t("status")}</Th>
                    <Th>{t("dueDate")}</Th>
                    <Th className="text-end">{t("cost")}</Th>
                    <Th className="text-end">{tc("actions")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((task) => (
                    <tr key={task.id} className={trClass}>
                      <td className={cn(tdClass, "max-w-sm")}>
                        <div className="font-medium break-words text-gray-900 dark:text-white/90">{task.description}</div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                          {task.calendar_closed_until && (
                            <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
                              <CalendarIcon className="size-3.5" /> {t("calendarClosed", { date: formatDateShort(task.calendar_closed_until) })}
                            </span>
                          )}
                          {task.photos.length > 0 && (
                            <span className="inline-flex items-center gap-1"><CameraIcon className="size-3.5" /> {task.photos.length}</span>
                          )}
                        </div>
                      </td>
                      <td className={tdClass}>{task.property_name}</td>
                      <td className={tdClass}>
                        <Badge variant="light" size="sm" color={PRIORITY_COLOR[task.priority]} className="[text-shadow:none]!">
                          {to(`priority.${task.priority}`)}
                        </Badge>
                      </td>
                      <td className={tdClass}>{to(`taskStatus.${task.status}`)}</td>
                      <td className={cn(tdClass, "whitespace-nowrap")}>{formatDateShort(task.due_date)}</td>
                      <td className={cn(tdClass, "text-end whitespace-nowrap")}>{task.cost ? formatCurrency(task.cost) : "—"}</td>
                      <td className={cn(tdClass, "text-end")}>
                        <div className="inline-flex gap-1">
                          <Button variant="ghost" size="icon-xs" aria-label={tc("edit")} onClick={() => { setEditing(task); setFormOpen(true); }}>
                            <PencilIcon className="size-4" />
                          </Button>
                          <Button variant="ghost" size="icon-xs" aria-label={tc("delete")} onClick={() => remove(task)}>
                            <TrashBinIcon className="size-4" />
                          </Button>
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
      <IssueFormDialog open={formOpen} issue={editing} properties={props} onOpenChange={setFormOpen} onSaved={list.reload} />
    </>
  );
}
