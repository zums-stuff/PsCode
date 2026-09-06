import { t } from "../lib/i18n";
import type { ClassMemberOut } from "../lib/types";

/** Read-only class member table — members self-register, no remove action. */
export default function MemberList({ members }: { members: ClassMemberOut[] }) {
  if (members.length === 0) {
    return <p>{t("admin.classes.members.empty")}</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>{t("admin.classes.members.username")}</th>
          <th>{t("admin.classes.members.role")}</th>
          <th>{t("admin.classes.members.joined")}</th>
        </tr>
      </thead>
      <tbody>
        {members.map((m) => (
          <tr key={m.user_id}>
            <td>{m.username}</td>
            <td>{m.role}</td>
            <td>{m.joined_at}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}