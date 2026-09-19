/** Mirrors the backend's own default-naming convention
 * (`tenants/repository.py::_default_tenant_name`) so a solo signup sees the
 * same suggestion whichever path provisions their workspace. The frontend
 * only ever has the email to work with — `AuthenticatedUser` doesn't expose
 * a first name. */
export function suggestWorkspaceName(email: string): string {
  const localPart = email.split("@", 1)[0]?.trim();
  const label = localPart || "user";
  return `${label}'s organization`;
}
