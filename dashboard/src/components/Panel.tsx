import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  subtitle?: string;
  className?: string;
  actions?: ReactNode;
  children: ReactNode;
}

/** Consistent titled card used across the §14 panel grid. */
export function Panel({ title, subtitle, className, actions, children }: PanelProps) {
  return (
    <section className={`panel ${className ?? ""}`}>
      <header className="panel__head">
        <div>
          <h2 className="panel__title">{title}</h2>
          {subtitle && <p className="panel__subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="panel__actions">{actions}</div>}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
