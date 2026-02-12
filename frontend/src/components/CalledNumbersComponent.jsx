export default function CalledNumbersComponent({ calledNumbers }) {
  const lastThree = [...calledNumbers].slice(-3).reverse();

  return (
    <section className="component" id="calledNumbersComponent">
      <div className="component-title">Called Numbers</div>
      <div className="numbers-stack">
        <div className="number-pill">{lastThree[0] ?? "—"}</div>
        <div className="number-pill">{lastThree[1] ?? "—"}</div>
        <div className="number-pill">{lastThree[2] ?? "—"}</div>
      </div>
      <div className="numbers-list">
        {calledNumbers.map((num) => (
          <span key={num}>{num}</span>
        ))}
      </div>
    </section>
  );
}
