import { getRole, homePath, isAuthenticated } from "@/lib/auth";
import { Navigate, Outlet, useLocation } from "react-router";

/** Giriş yapılmamışsa içindeki route'lara izin vermez ve /signin'e yönlendirir.
 *  Temizlikçi rolü sadece /cleaner görünümünü kullanır (yetkiyi ayrıca backend uygular). */
export function ProtectedRoute() {
  const { pathname } = useLocation();
  if (!isAuthenticated()) return <Navigate to="/signin" replace />;
  if (getRole() === "cleaner" && pathname !== "/cleaner") return <Navigate to="/cleaner" replace />;
  return <Outlet />;
}

/** Zaten giriş yapılmışsa (ör. /signin) kendi ana sayfasına yönlendirir. */
export function PublicOnlyRoute() {
  return isAuthenticated() ? <Navigate to={homePath()} replace /> : <Outlet />;
}
