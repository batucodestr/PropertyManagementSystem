import { PageMeta } from "@/components/shared/page-meta";
import { SelectField, TextField } from "@/components/shared/pms/form-bits";
import { EmptyState, ErrorBanner, LoadingBlock, PageHeader, Panel } from "@/components/shared/pms/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useApiAll } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { InfoCircleIcon, PencilIcon, PlusIcon, TrashBinIcon } from "@/icons";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import type { MessageTemplate, MessageTrigger } from "@/lib/pms/types";
import { useRef, useState } from "react";

const TRIGGERS: MessageTrigger[] = ["booking_confirmed", "before_check_in", "check_in_day", "check_out_morning", "after_check_out"];
const VARIABLES = [
  "guest_first_name", "guest_last_name", "property_name", "check_in_date", "check_in_time", "check_out_date",
  "check_out_time", "nights", "address", "wifi_name", "wifi_password", "door_code", "check_in_instructions",
  "house_rules", "booking_ref",
];
const usesSendTime = (trigger: string) => trigger === "check_in_day" || trigger === "check_out_morning";

export default function MessageTemplatesPage() {
  const t = useTranslations("pms.templates");
  const tc = useTranslations("pms.finance.common");
  const list = useApiAll<MessageTemplate>("/messaging/templates/");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const timing = (tpl: MessageTemplate) =>
    usesSendTime(tpl.trigger)
      ? `${t(`triggers.${tpl.trigger}`)} · ${(tpl.send_time ?? (tpl.trigger === "check_in_day" ? "10:00" : "08:00")).slice(0, 5)}`
      : `${t(`triggers.${tpl.trigger}`)}${tpl.offset_hours ? ` · ${tpl.offset_hours}h` : ""}`;

  const remove = async (tpl: MessageTemplate) => {
    if (!window.confirm(t("deleteConfirm", { name: tpl.name }))) return;
    setActionError(null);
    try {
      await api.delete(`/messaging/templates/${tpl.id}/`);
      list.reload();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader title={t("title")} description={t("description")}
        actions={<Button onClick={() => { setEditing(null); setOpen(true); }}><PlusIcon /> {t("add")}</Button>} />
      <p className="mb-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <InfoCircleIcon className="size-4 shrink-0" /> {t("emailNote")}
      </p>
      {actionError && <ErrorBanner className="mb-4" message={actionError} />}
      <Panel>
        {list.error ? (
          <div className="p-4"><ErrorBanner message={list.error} onRetry={list.reload} /></div>
        ) : !list.data ? (
          <LoadingBlock />
        ) : list.data.length === 0 ? (
          <EmptyState title={t("empty")} description={t("emptyDescription")} />
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {list.data.map((tpl) => (
              <li key={tpl.id} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-white/90">{tpl.name}</span>
                    <Badge variant="light" size="sm" color="gray" className="[text-shadow:none]! uppercase">{tpl.language}</Badge>
                    {!tpl.is_active && <Badge variant="light" size="sm" color="warning" className="[text-shadow:none]!">{t("inactive")}</Badge>}
                  </div>
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">{timing(tpl)}</p>
                  <p className="mt-1 line-clamp-2 text-sm whitespace-pre-line text-gray-600 dark:text-gray-400">{tpl.body}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="icon-xs" aria-label={`${tc("edit")} ${tpl.name}`} onClick={() => { setEditing(tpl); setOpen(true); }}>
                    <PencilIcon className="size-4" />
                  </Button>
                  <Button variant="ghost" size="icon-xs" aria-label={`${tc("delete")} ${tpl.name}`} onClick={() => remove(tpl)}>
                    <TrashBinIcon className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>{editing ? t("editTitle") : t("addTitle")}</DialogTitle></DialogHeader>
          {open && <TemplateForm key={editing?.id ?? "new"} template={editing} onCancel={() => setOpen(false)}
            onSaved={() => { setOpen(false); list.reload(); }} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function TemplateForm({ template, onCancel, onSaved }: {
  template: MessageTemplate | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("pms.templates");
  const tc = useTranslations("pms.finance.common");
  const [name, setName] = useState(template?.name ?? "");
  const [trigger, setTrigger] = useState<string>(template?.trigger ?? "before_check_in");
  const [offset, setOffset] = useState(String(template?.offset_hours ?? 24));
  const [sendTime, setSendTime] = useState((template?.send_time ?? "").slice(0, 5));
  const [language, setLanguage] = useState(template?.language ?? "en");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const [active, setActive] = useState(template?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const insert = (variable: string) => {
    const token = `{${variable}}`;
    const el = bodyRef.current;
    if (!el) { setBody((b) => b + token); return; }
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + token + body.slice(end));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const payload = {
      name, trigger, language, subject, body, is_active: active,
      offset_hours: usesSendTime(trigger) ? 0 : Number(offset || 0),
      send_time: usesSendTime(trigger) && sendTime ? sendTime : null,
    };
    try {
      if (template) await api.patch(`/messaging/templates/${template.id}/`, payload);
      else await api.post("/messaging/templates/", payload);
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
      <form id="template-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <ErrorBanner className="sm:col-span-2" message={error} />}
        <TextField label={t("name")} value={name} onChange={setName} error={errors.name} required />
        <TextField label={t("language")} value={language} onChange={setLanguage} error={errors.language} placeholder="en, tr…" />
        <SelectField label={t("trigger")} value={trigger} onChange={setTrigger} error={errors.trigger}
          options={TRIGGERS.map((x) => ({ value: x, label: t(`triggers.${x}`) }))} />
        {usesSendTime(trigger) ? (
          <TextField label={t("sendTime")} type="time" value={sendTime} onChange={setSendTime} error={errors.send_time}
            placeholder={trigger === "check_in_day" ? "10:00" : "08:00"} />
        ) : (
          <TextField label={t("offsetHours")} type="number" value={offset} onChange={setOffset} error={errors.offset_hours} />
        )}
        <p className="-mt-2 text-xs text-gray-500 sm:col-span-2 dark:text-gray-400">{t(`offsetHint.${trigger}`)}</p>
        <TextField className="sm:col-span-2" label={t("subject")} value={subject} onChange={setSubject} error={errors.subject} />
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label htmlFor="template-body" className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("body")}</label>
          <Textarea id="template-body" ref={bodyRef} rows={8} value={body} onChange={(e) => setBody(e.target.value)} aria-invalid={!!errors.body} />
          {errors.body && <p className="text-xs text-red-500">{errors.body}</p>}
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("variables")}</p>
          <div className="flex flex-wrap gap-1.5">
            {VARIABLES.map((v) => (
              <button key={v} type="button" onClick={() => insert(v)}
                className="rounded-md border border-gray-200 px-2 py-0.5 font-mono text-xs text-gray-700 hover:border-brand-300 hover:text-brand-600 dark:border-gray-700 dark:text-gray-300 dark:hover:text-brand-400">
                {`{${v}}`}
              </button>
            ))}
          </div>
        </div>
        <label className="flex items-center gap-2.5 text-sm text-gray-700 sm:col-span-2 dark:text-gray-300">
          <Checkbox checked={active} onCheckedChange={(c) => setActive(c === true)} /> {t("active")}
        </label>
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>{tc("cancel")}</Button>
        <Button type="submit" form="template-form" disabled={saving}>{tc("save")}</Button>
      </DialogFooter>
    </>
  );
}
