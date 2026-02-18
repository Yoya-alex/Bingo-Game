export default function HeaderComponent({ title, subtitle, stats }) {
  return (
    <div className="component">
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <div className="title">{title}</div>
        <div className="subtitle">{subtitle}</div>
      </div>
      <div className="stat-strip" style={{ marginTop: "16px" }}>
        {stats.map((stat) => (
          <div className="stat-item" key={stat.label}>
            <span>{stat.label}</span>
            <div className="stat-value">{stat.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
