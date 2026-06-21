export function PlaceholderPage({ title, description }: { title: string; description?: string }) {
  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)" }}>{title}</div>
          {description && <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>{description}</div>}
        </div>
      </div>
    </div>
  );
}
