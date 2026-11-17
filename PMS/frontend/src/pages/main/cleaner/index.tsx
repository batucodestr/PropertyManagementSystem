import { PageMeta } from "@/components/shared/page-meta";
import { ErrorBanner, LoadingBlock } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useTranslations } from "@/i18n";
import { CameraIcon, CheckCircleIcon, LogOutIcon, MapIcon, RegenerateIcon } from "@/icons";
import { api, apiFetch, errorMessage, signOut } from "@/lib/api";
import { getUsername } from "@/lib/auth";
import { formatDate, todayISO, toISODate } from "@/lib/pms/format";
import type { CleanerTask } from "@/lib/pms/types";
import { cn } from "@/utils";
import { addDays, format, parseISO } from "date-fns";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";

/** Temizlikçi (mobil) görünümü: sadece kendisine atanmış bugünkü / yarınki görevler. */
export default function CleanerPage() {
  const t = useTranslations("pms.cleaner");
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<CleanerTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<CleanerTask[]>("/cleaner/tasks/")
      .then((d) => { setTasks(d); setError(null); })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const replace = (task: CleanerTask) => setTasks((list) => list?.map((x) => (x.id === task.id ? task : x)) ?? null);

  const today = todayISO();
  const tomorrow = toISODate(addDays(parseISO(today), 1));
  const groups: [string, CleanerTask[]][] = [
    [t("earlier"), (tasks ?? []).filter((x) => x.scheduled_date < today)],
    [t("today"), (tasks ?? []).filter((x) => x.scheduled_date === today)],
    [t("tomorrow"), (tasks ?? []).filter((x) => x.scheduled_date === tomorrow)],
  ];

  const logout = async () => {
    await signOut();
    void navigate("/signin", { replace: true });
  };

  return (
    <div className="min-h-dvh bg-gray-50 dark:bg-gray-950">
      <PageMeta title={`${t("title")} | PMS Console`} description={t("title")} />
      <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900">
        <div>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-white/90">{t("title")}</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">{getUsername()}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" aria-label={t("refresh")} onClick={load}><RegenerateIcon className="size-5" /></Button>
          <Button variant="outline" size="icon" aria-label={t("signOut")} onClick={logout}><LogOutIcon className="size-5" /></Button>
        </div>
      </header>

      <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 py-5">
        {error && <ErrorBanner message={error} onRetry={load} />}
        {!tasks && !error ? (
          <LoadingBlock />
        ) : tasks && tasks.length === 0 ? (
          <p className="py-16 text-center text-gray-500 dark:text-gray-400">{t("empty")}</p>
        ) : (
          groups.filter(([, list]) => list.length).map(([label, list]) => (
            <section key={label} className="flex flex-col gap-3">
              <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">{label}</h2>
              {list.map((task) => <TaskCard key={task.id} task={task} onChange={replace} />)}
            </section>
          ))
        )}
      </main>
    </div>
  );
}

function TaskCard({ task, onChange }: { task: CleanerTask; onChange: (t: CleanerTask) => void }) {
  const t = useTranslations("pms.cleaner");
  const [notes, setNotes] = useState(task.notes);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const done = task.status === "completed";

  const call = async (key: string, run: () => Promise<CleanerTask>) => {
    setBusy(key);
    setError(null);
    try {
      onChange(await run());
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const base = `/cleaner/tasks/${task.id}/`;
  const upload = (file: File) => {
    const form = new FormData();
    form.append("image", file);
    void call("photo", () => apiFetch<CleanerTask>(base + "photos/", { method: "POST", body: form }));
  };

  return (
    <article
      className={cn(
        "rounded-2xl border bg-white p-4 shadow-theme-xs dark:bg-gray-900",
        task.priority === "urgent" && !done ? "border-red-300 dark:border-red-500/40" : "border-gray-200 dark:border-gray-800",
        done && "opacity-75",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">{task.property_name}</h3>
          <p className="mt-0.5 flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400">
            <MapIcon className="size-4 shrink-0" /> {task.property_address}
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{formatDate(task.scheduled_date)}</p>
        </div>
        {task.priority === "urgent" && !done && (
          <span className="shrink-0 rounded-lg bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 dark:bg-red-500/15 dark:text-red-300">
            {t("urgent")}
          </span>
        )}
      </div>
      {task.next_check_in && (
        <p className="mt-3 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:bg-white/5 dark:text-gray-300">
          {t("nextCheckIn", { time: format(parseISO(task.next_check_in.check_in), "dd MMM HH:mm"), guests: task.next_check_in.guests })}
        </p>
      )}

      {error && <ErrorBanner className="mt-3" message={error} />}

      <div className="mt-4 grid grid-cols-2 gap-3">
        {done ? (
          <p className="col-span-2 flex items-center justify-center gap-2 rounded-xl bg-emerald-50 py-4 text-base font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
            <CheckCircleIcon className="size-5" /> {t("completed")}
          </p>
        ) : (
          <>
            <Button size="lg" variant={task.status === "in_progress" ? "outline" : "default"} className="h-14 text-base"
              disabled={!!busy || task.status === "in_progress"}
              onClick={() => void call("start", () => api.post<CleanerTask>(base + "start/"))}>
              {busy === "start" ? <Spinner /> : null} {t("start")}
            </Button>
            <Button size="lg" className="h-14 bg-emerald-600 text-base hover:bg-emerald-700" disabled={!!busy}
              onClick={() => void call("done", () => api.post<CleanerTask>(base + "complete/", { notes }))}>
              {busy === "done" ? <Spinner /> : null} {t("done")}
            </Button>
          </>
        )}
      </div>

      <div className="mt-4 flex flex-col gap-2">
        <label htmlFor={`notes-${task.id}`} className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("notes")}</label>
        <Textarea id={`notes-${task.id}`} rows={2} value={notes} placeholder={t("notesPlaceholder")}
          onChange={(e) => { setNotes(e.target.value); setSaved(false); }} />
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" disabled={!!busy || notes === task.notes}
            onClick={async () => setSaved(await call("notes", () => api.post<CleanerTask>(base + "notes/", { notes })))}>
            {t("saveNotes")}
          </Button>
          {saved && <span role="status" className="text-sm text-emerald-600">{t("notesSaved")}</span>}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {task.photos.map((p) => (
          <a key={p.id} href={p.image} target="_blank" rel="noreferrer">
            <img src={p.image} alt="" className="size-16 rounded-lg object-cover" loading="lazy" />
          </a>
        ))}
        <label className={cn(
          "flex size-16 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-gray-300 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400",
          busy === "photo" && "pointer-events-none opacity-60",
        )}>
          {busy === "photo" ? <Spinner /> : <CameraIcon className="size-5" />}
          <span className="sr-only">{t("addPhoto")}</span>
          <input type="file" accept="image/*" capture="environment" className="sr-only"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
        </label>
      </div>
    </article>
  );
}
