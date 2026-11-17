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
import { Spinner } from "@/components/ui/spinner";
import { useTranslations } from "@/i18n";
import { CameraIcon, TrashBinIcon } from "@/icons";
import { api, apiFetch, errorMessage, fieldErrors } from "@/lib/api";
import { todayISO } from "@/lib/pms/format";
import type { GeneralTask, Property, TaskPhoto, TaskPriority, TaskStatus, TaskType } from "@/lib/pms/types";
import { useState } from "react";

const PRIORITIES: TaskPriority[] = ["low", "normal", "high", "critical"];
const STATUSES: TaskStatus[] = ["pending", "in_progress", "completed"];
const TYPES: TaskType[] = ["maintenance", "inspection", "general"];

export function IssueFormDialog({ open, issue, properties, onOpenChange, onSaved }: {
  open: boolean;
  issue: GeneralTask | null;
  properties: Property[];
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.maintenance");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{issue ? t("editTitle") : t("addTitle")}</DialogTitle>
        </DialogHeader>
        {open && (
          <IssueForm key={issue?.id ?? "new"} issue={issue} properties={properties}
            onCancel={() => onOpenChange(false)} onSaved={() => { onSaved(); onOpenChange(false); }} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function IssueForm({ issue, properties, onCancel, onSaved }: {
  issue: GeneralTask | null;
  properties: Property[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.maintenance");
  const to = useTranslations("pms.ops");
  const tc = useTranslations("pms.finance.common");
  const [property, setProperty] = useState(issue?.property ?? properties[0]?.id ?? "");
  const [description, setDescription] = useState(issue?.description ?? "");
  const [taskType, setTaskType] = useState<string>(issue?.task_type ?? "maintenance");
  const [priority, setPriority] = useState<string>(issue?.priority ?? "normal");
  const [status, setStatus] = useState<string>(issue?.status ?? "pending");
  const [dueDate, setDueDate] = useState(issue?.due_date ?? todayISO());
  const [cost, setCost] = useState(issue?.cost ?? "");
  const [closeUntil, setCloseUntil] = useState(issue?.calendar_closed_until ?? "");
  const [photos, setPhotos] = useState<TaskPhoto[]>(issue?.photos ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = {
      property, description, task_type: taskType, priority, status, due_date: dueDate,
      cost: cost === "" ? null : cost,
      close_calendar_until: closeUntil || null,
    };
    try {
      if (issue) await api.patch(`/general-tasks/${issue.id}/`, body);
      else await api.post("/general-tasks/", body);
      onSaved();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      if (!Object.keys(fe).length || fe.non_field_errors) setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const upload = async (file: File) => {
    if (!issue) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("general_task", issue.id);
      form.append("image", file);
      const photo = await apiFetch<TaskPhoto>("/task-photos/", { method: "POST", body: form });
      setPhotos((p) => [...p, photo]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const removePhoto = async (photo: TaskPhoto) => {
    try {
      await api.delete(`/task-photos/${photo.id}/`);
      setPhotos((p) => p.filter((x) => x.id !== photo.id));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <>
      <form id="issue-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <ErrorBanner className="sm:col-span-2" message={error} />}
        <SelectField label={tc("property")} value={property} onChange={setProperty} error={errors.property}
          options={properties.map((p) => ({ value: p.id, label: p.name }))} />
        <SelectField label={t("type")} value={taskType} onChange={setTaskType} error={errors.task_type}
          options={TYPES.map((x) => ({ value: x, label: t(`types.${x}`) }))} />
        <div className="sm:col-span-2">
          <TextAreaField label={t("issue")} value={description} onChange={setDescription} rows={3} />
          {errors.description && <p className="mt-1 text-xs text-red-500">{errors.description}</p>}
        </div>
        <SelectField label={t("priority")} value={priority} onChange={setPriority} error={errors.priority}
          options={PRIORITIES.map((x) => ({ value: x, label: to(`priority.${x}`) }))} />
        <SelectField label={t("status")} value={status} onChange={setStatus} error={errors.status}
          options={STATUSES.map((x) => ({ value: x, label: to(`taskStatus.${x}`) }))} />
        <TextField label={t("dueDate")} type="date" value={dueDate} onChange={setDueDate} error={errors.due_date} required />
        <div>
          <TextField label={t("cost")} type="number" value={cost} onChange={setCost} error={errors.cost} />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("costHint")}</p>
        </div>
        <div className="sm:col-span-2">
          <TextField label={t("closeCalendar")} type="date" value={closeUntil} onChange={setCloseUntil} error={errors.close_calendar_until} />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("closeCalendarHint")}</p>
        </div>
        <div className="sm:col-span-2">
          <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">{to("photos")}</p>
          {issue ? (
            <div className="flex flex-wrap items-center gap-2">
              {photos.map((p) => (
                <div key={p.id} className="group relative">
                  <a href={p.image} target="_blank" rel="noreferrer"><img src={p.image} alt="" className="size-16 rounded-lg object-cover" /></a>
                  <button type="button" aria-label={tc("delete")} onClick={() => removePhoto(p)}
                    className="absolute -end-1.5 -top-1.5 hidden rounded-full bg-white p-1 text-gray-600 shadow-theme-sm group-hover:block dark:bg-gray-800 dark:text-gray-300">
                    <TrashBinIcon className="size-3.5" />
                  </button>
                </div>
              ))}
              <label className="flex size-16 cursor-pointer items-center justify-center rounded-lg border border-dashed border-gray-300 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                {uploading ? <Spinner /> : <CameraIcon className="size-5" />}
                <span className="sr-only">{to("addPhoto")}</span>
                <input type="file" accept="image/*" className="sr-only"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
              </label>
            </div>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400">{t("photosHint")}</p>
          )}
        </div>
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{tc("cancel")}</Button>
        <Button type="submit" form="issue-form" disabled={saving}>{tc("save")}</Button>
      </DialogFooter>
    </>
  );
}
