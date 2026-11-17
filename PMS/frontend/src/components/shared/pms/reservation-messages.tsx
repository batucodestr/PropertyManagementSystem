import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiAll } from "@/hooks/use-api";
import { useTranslations } from "@/i18n";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/pms/format";
import type { ScheduledMessage, ScheduledStatus } from "@/lib/pms/types";
import { useState } from "react";
import { Link } from "react-router";

const STATUS_COLOR: Record<ScheduledStatus, "info" | "success" | "error" | "gray" | "warning"> = {
  pending: "info", sending: "warning", sent: "success", failed: "error", cancelled: "gray", skipped: "gray",
};

/** Rezervasyon detayında planlanmış / gönderilmiş otomatik mesajlar. */
export function ReservationMessages({ reservationId }: { reservationId: string }) {
  const t = useTranslations("pms.reservationMessages");
  const tt = useTranslations("pms.templates");
  const list = useApiAll<ScheduledMessage>("/messaging/scheduled/", { reservation: reservationId });
  const [error, setError] = useState<string | null>(null);

  const cancel = async (m: ScheduledMessage) => {
    setError(null);
    try {
      await api.post(`/messaging/scheduled/${m.id}/cancel/`);
      list.reload();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <section>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-xs tracking-wide text-gray-500 uppercase dark:text-gray-400">{t("title")}</h4>
        <Link to="/inbox" className="text-xs font-medium text-brand-500 hover:underline dark:text-brand-400">{t("openInbox")}</Link>
      </div>
      {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
      {list.data && list.data.length === 0 && <p className="text-sm text-gray-500 dark:text-gray-400">{t("empty")}</p>}
      <ul className="space-y-2">
        {(list.data ?? []).map((m) => (
          <li key={m.id} className="flex items-start justify-between gap-2 rounded-lg border border-gray-100 px-3 py-2 dark:border-gray-800">
            <div className="min-w-0">
              <p className="truncate text-sm text-gray-800 dark:text-white/90">{m.template_name}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {tt(`triggers.${m.trigger}`)} · {formatDateTime(m.sent_at ?? m.send_at)}
              </p>
              {m.error && <p className="mt-0.5 text-xs break-words text-red-500">{m.error}</p>}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge variant="light" size="sm" color={STATUS_COLOR[m.status]} className="[text-shadow:none]!">{t(`status.${m.status}`)}</Badge>
              {m.status === "pending" && (
                <Button variant="ghost" size="xs" onClick={() => cancel(m)}>{t("cancel")}</Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
