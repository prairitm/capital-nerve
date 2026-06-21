import type { ReactNode } from "react";

export function Empty({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="card p-8 text-center flex flex-col items-center gap-3">
      {icon && <div className="text-ink-mute">{icon}</div>}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {description && <p className="text-sm text-ink-mute max-w-md">{description}</p>}
      {action}
    </div>
  );
}
