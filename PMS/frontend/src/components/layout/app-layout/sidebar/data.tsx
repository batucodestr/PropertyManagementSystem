import {
  BarChartIcon,
  BrushIcon,
  ChatIcon,
  DocIcon,
  DollarIcon,
  PluginIcon,
  UserDollarIcon,
  CalendarIcon,
  GearIcon,
  LayerIcon,
  LayoutGridIcon,
  MapIcon,
  TicketIcon,
  UsersIcon,
  ArrowLeftRightIcon,
} from "@/icons";
import type { NavGroup } from "./types";

const icon = "size-5";

/** PMS navigation. Labels live under `sidebar.items.<key>` in src/messages. */
export const navGroups: NavGroup[] = [
  {
    type: "overview",
    labelKey: "groups.overview",
    items: [
      {
        key: "dashboard",
        icon: <LayoutGridIcon className={icon} />,
        path: "/dashboard",
      },
    ],
  },
  {
    type: "property",
    labelKey: "groups.propertyManagement",
    items: [
      { key: "properties", icon: <MapIcon className={icon} />, path: "/properties" },
      { key: "reservations", icon: <TicketIcon className={icon} />, path: "/reservations" },
      { key: "calendar", icon: <CalendarIcon className={icon} />, path: "/calendar" },
      { key: "rates", icon: <DollarIcon className={icon} />, path: "/rates" },
      { key: "guests", icon: <UsersIcon className={icon} />, path: "/guests" },
    ],
  },
  {
    type: "operations",
    labelKey: "groups.operations",
    items: [
      { key: "housekeeping", icon: <BrushIcon className={icon} />, path: "/housekeeping" },
      { key: "checkInOut", icon: <ArrowLeftRightIcon className={icon} />, path: "/operations" },
      { key: "tasks", icon: <LayerIcon className={icon} />, path: "/tasks" },
      { key: "inbox", icon: <ChatIcon className={icon} />, path: "/inbox" },
    ],
  },
  {
    type: "finance",
    labelKey: "groups.finance",
    items: [
      { key: "payments", icon: <UserDollarIcon className={icon} />, path: "/finance/payments" },
      { key: "reports", icon: <BarChartIcon className={icon} />, path: "/finance/reports" },
    ],
  },
  {
    type: "system",
    labelKey: "groups.system",
    items: [
      { key: "channels", icon: <PluginIcon className={icon} />, path: "/channels" },
      { key: "syncLog", icon: <DocIcon className={icon} />, path: "/sync-log" },
      { key: "settings", icon: <GearIcon className={icon} />, path: "/settings" },
    ],
  },
];

