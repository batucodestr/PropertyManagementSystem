import { PageMeta } from "@/components/shared/page-meta";
import { SyncNowButton } from "@/components/shared/pms/channel-status";
import {
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
  Panel,
  Th,
  tdClass,
  theadClass,
  trClass,
} from "@/components/shared/pms/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useTranslations } from "@/i18n";
import { InfoCircleIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/pms/format";
import type { ChannelListing, ChannelOverview, SyncStatus } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useCallback, useEffect, useState } from "react";

const STATUS_COLOR: Record<SyncStatus, "success" | "warning" | "error"> = {
  ok: "success",
  pending: "warning",
  error: "error",
};

function Notice({ tone = "info", children }: { tone?: "info" | "warning"; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm",
        tone === "warning"
          ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
          : "border-brand-200 bg-brand-50 text-brand-800 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200",
      )}
    >
      <InfoCircleIcon className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export default function ChannelsPage() {
  const t = useTranslations("pms.channels");
  const [data, setData] = useState<ChannelOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<ChannelOverview>("/integrations/channels/")
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const replaceListing = (listing: ChannelListing) =>
    setData((d) => d && {
      ...d,
      results: d.results.map((r) => (r.property.id === listing.property ? { ...r, listing } : r)),
    });

  const toggle = async (listing: ChannelListing, field: "airbnb_connected" | "booking_connected", value: boolean) => {
    setActionError(null);
    replaceListing({ ...listing, [field]: value });
    try {
      replaceListing(await api.patch<ChannelListing>(`/integrations/listings/${listing.id}/`, { [field]: value }));
    } catch (e) {
      replaceListing(listing);
      setActionError(errorMessage(e));
    }
  };

  return (
    <>
      <PageMeta title={`${t("title")} | PMS Console`} description={t("metaDescription")} />
      <PageHeader title={t("title")} description={t("description")} />

      <div className="mb-4 flex flex-col gap-3">
        {data && !data.configured && <Notice tone="warning">{t("notConfigured")}</Notice>}
        {data && data.configured && !data.webhook_configured && <Notice tone="warning">{t("webhookMissing")}</Notice>}
        {data && !data.photos_supported && <Notice>{t("photosWarning")}</Notice>}
        {data?.channel_status_manual && <Notice>{t("manualStatus")}</Notice>}
        {actionError && <ErrorBanner message={actionError} />}
      </div>

      <Panel
        title="Beds24"
        description={data ? (data.last_poll_at ? t("lastPoll", { time: formatDateTime(data.last_poll_at) }) : t("neverPolled")) : undefined}
      >
        {error ? (
          <div className="p-4"><ErrorBanner message={error} onRetry={load} /></div>
        ) : !data ? (
          <LoadingBlock />
        ) : data.results.length === 0 ? (
          <EmptyState title={t("empty")} description={t("emptyDescription")} />
        ) : (
          <div className="custom-scrollbar overflow-x-auto">
            <table className="min-w-full">
              <thead className={theadClass}>
                <tr>
                  <Th>{t("property")}</Th>
                  <Th>{t("beds24")}</Th>
                  <Th>{t("airbnb")}</Th>
                  <Th>{t("booking")}</Th>
                  <Th>{t("status")}</Th>
                  <Th>{t("lastSynced")}</Th>
                  <Th className="text-end">{t("actions")}</Th>
                </tr>
              </thead>
              <tbody>
                {data.results.map(({ property, listing }) => (
                  <tr key={property.id} className={trClass}>
                    <td className={tdClass}>
                      <div className="font-medium text-gray-900 dark:text-white/90">{property.name}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {property.city}
                        {!property.is_active && <> · {t("inactive")}</>}
                      </div>
                    </td>
                    <td className={cn(tdClass, "whitespace-nowrap")}>
                      {listing ? t("propertyRoom", { property: listing.external_listing_id, room: listing.external_room_id || "—" }) : "—"}
                    </td>
                    {(["airbnb_connected", "booking_connected"] as const).map((field) => (
                      <td key={field} className={tdClass}>
                        {listing ? (
                          <Switch
                            size="sm"
                            checked={listing[field]}
                            aria-label={t("connectedToggle", { channel: t(field === "airbnb_connected" ? "airbnb" : "booking"), property: property.name })}
                            onCheckedChange={(checked) => toggle(listing, field, checked)}
                          />
                        ) : "—"}
                      </td>
                    ))}
                    <td className={tdClass}>
                      {listing ? (
                        <div className="flex flex-col gap-1">
                          <Badge variant="light" size="sm" color={STATUS_COLOR[listing.sync_status]} className="[text-shadow:none]!">
                            {t(`status_${listing.sync_status}`)}
                          </Badge>
                          {listing.last_error && (
                            <span className="max-w-xs text-xs break-words text-red-600 dark:text-red-400">{listing.last_error}</span>
                          )}
                        </div>
                      ) : "—"}
                    </td>
                    <td className={cn(tdClass, "whitespace-nowrap")}>
                      {listing?.last_synced_at ? formatDateTime(listing.last_synced_at) : t("never")}
                    </td>
                    <td className={cn(tdClass, "text-end")}>
                      <SyncNowButton
                        propertyId={property.id}
                        onDone={(l) => { setActionError(null); replaceListing(l); }}
                        onError={(m) => { setActionError(m); load(); }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
