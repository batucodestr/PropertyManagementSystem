import { PageMeta } from "@/components/shared/page-meta";
import { CHANNEL_STYLES } from "@/components/shared/pms/badges";
import { EmptyState, ErrorBanner, LoadingBlock, PageHeader, Panel, SearchBox } from "@/components/shared/pms/ui-bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useApiList, useDebounce } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { ChevronLeftIcon, MailIcon, SendIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import { formatDateShort, formatDateTime } from "@/lib/pms/format";
import { SOURCE_LABELS } from "@/lib/pms/labels";
import type { Conversation, InboxMessage } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useCallback, useEffect, useRef, useState } from "react";

const REFRESH_MS = 30_000;

export default function InboxPage() {
  const t = useTranslations("pms.inbox");
  const [search, setSearch] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const debounced = useDebounce(search.trim());
  const list = useApiList<Conversation>("/messaging/conversations/", {
    search: debounced, unread: unreadOnly ? "true" : "", page_size: 35,
  });
  const reload = list.reload;
  useEffect(() => {
    const id = setInterval(reload, REFRESH_MS);
    return () => clearInterval(id);
  }, [reload]);

  const conversations = list.data?.results ?? [];

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader title={t("title")} />
      <Panel bodyClassName="grid h-[calc(100dvh-14rem)] min-h-[480px] grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className={cn("flex min-h-0 flex-col border-gray-100 lg:border-e dark:border-gray-800", selected && "hidden lg:flex")}>
          <div className="flex flex-col gap-2 border-b border-gray-100 p-3 dark:border-gray-800">
            <SearchBox className="sm:w-full" value={search} onChange={setSearch} placeholder={t("searchPlaceholder")} />
            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <Checkbox checked={unreadOnly} onCheckedChange={(c) => setUnreadOnly(c === true)} /> {t("unreadOnly")}
            </label>
          </div>
          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
            {list.error ? (
              <div className="p-3"><ErrorBanner message={list.error} onRetry={reload} /></div>
            ) : !list.data ? (
              <LoadingBlock />
            ) : conversations.length === 0 ? (
              <EmptyState title={t("empty")} description={t("emptyDescription")} />
            ) : (
              <ul>
                {conversations.map((c) => {
                  const style = c.channel === "email" ? null : CHANNEL_STYLES[c.source] ?? CHANNEL_STYLES.other;
                  return (
                    <li key={c.id}>
                      <button type="button" onClick={() => setSelected(c)}
                        className={cn(
                          "flex w-full flex-col gap-1 border-b border-gray-100 px-4 py-3 text-start transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-white/3",
                          selected?.id === c.id && "bg-brand-50/60 dark:bg-brand-500/10",
                        )}>
                        <span className="flex items-center justify-between gap-2">
                          <span className={cn("truncate text-sm text-gray-900 dark:text-white/90", c.unread_count > 0 && "font-semibold")}>
                            {c.guest_name}
                          </span>
                          {c.unread_count > 0 && (
                            <span className="rounded-full bg-brand-500 px-1.5 text-xs font-semibold text-white">{c.unread_count}</span>
                          )}
                        </span>
                        <span className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                          {style ? <span className={cn("size-2 rounded-full", style.dot)} /> : <MailIcon className="size-3.5" />}
                          {c.channel === "email" ? t("emailChannel") : SOURCE_LABELS[c.source]} · {c.property_name}
                          · {formatDateShort(c.check_in)}
                        </span>
                        <span className="truncate text-xs text-gray-500 dark:text-gray-400">{c.last_message_preview}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>
        <section className={cn("flex min-h-0 flex-col", !selected && "hidden lg:flex")}>
          {selected ? (
            <Thread key={selected.id} conversation={selected} onBack={() => setSelected(null)} onChanged={reload} />
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400">{t("selectConversation")}</div>
          )}
        </section>
      </Panel>
    </>
  );
}

function Thread({ conversation, onBack, onChanged }: { conversation: Conversation; onBack: () => void; onChanged: () => void }) {
  const t = useTranslations("pms.inbox");
  const [messages, setMessages] = useState<InboxMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const base = `/messaging/conversations/${conversation.id}/`;

  const load = useCallback(() => {
    api.get<InboxMessage[]>(base + "messages/")
      .then((m) => { setMessages(m); setError(null); })
      .catch((e) => setError(errorMessage(e)));
  }, [base]);

  useEffect(() => {
    load();
    if (conversation.unread_count > 0) {
      api.post(base + "read/").then(onChanged).catch(() => undefined);
    }
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load, base, conversation.unread_count, onChanged]);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    setSending(true);
    setError(null);
    try {
      await api.post(base + "reply/", { body });
      setBody("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
      load();
    }
  };

  const who = (m: InboxMessage) =>
    m.source === "system" ? t("system") : m.direction === "out" ? (m.sent_by_name ?? t("you")) : t("guest");

  return (
    <>
      <header className="flex items-center gap-3 border-b border-gray-100 px-4 py-3 dark:border-gray-800">
        <Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label="Back" onClick={onBack}>
          <ChevronLeftIcon className="size-4 rtl:rotate-180" />
        </Button>
        <div className="min-w-0">
          <p className="truncate font-medium text-gray-900 dark:text-white/90">{conversation.guest_name}</p>
          <p className="truncate text-xs text-gray-500 dark:text-gray-400">
            {conversation.property_name} · {formatDateShort(conversation.check_in)} – {formatDateShort(conversation.check_out)}
          </p>
        </div>
      </header>
      <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto bg-gray-50/60 px-4 py-4 dark:bg-white/2">
        {!messages && !error && <LoadingBlock />}
        {messages?.map((m) => (
          <div key={m.id} className={cn("flex", m.direction === "out" ? "justify-end" : "justify-start")}>
            <div className={cn(
              "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-line",
              m.direction === "out"
                ? "bg-brand-500 text-white"
                : "border border-gray-200 bg-white text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200",
              m.status === "failed" && "bg-red-50 text-red-800 ring-1 ring-red-300 dark:bg-red-500/10 dark:text-red-200",
            )}>
              {m.body}
              <div className={cn("mt-1 text-[11px]", m.direction === "out" && m.status !== "failed" ? "text-white/75" : "text-gray-500 dark:text-gray-400")}>
                {who(m)} · {formatDateTime(m.sent_at)}{m.status === "failed" && ` · ${t("failed")}`}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form onSubmit={send} className="flex flex-col gap-2 border-t border-gray-100 p-3 dark:border-gray-800">
        {error && <ErrorBanner message={error} />}
        {conversation.channel === "email" && <p className="text-xs text-gray-500 dark:text-gray-400">{t("emailNoInbound")}</p>}
        <Textarea rows={3} value={body} placeholder={t("replyPlaceholder")} onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void send(e); }} />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button type="submit" disabled={sending || !body.trim()}>
            {sending ? <Spinner /> : <SendIcon className="size-4" />} {sending ? t("sending") : t("send")}
          </Button>
        </div>
      </form>
    </>
  );
}
