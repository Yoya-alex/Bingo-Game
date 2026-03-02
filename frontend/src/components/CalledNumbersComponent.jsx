import { useMemo } from "react";

export default function CalledNumbersComponent({ calledNumbers, maxNumber = 400, onNumberClick, interactive = true }) {
  const calledSet = useMemo(() => new Set(calledNumbers || []), [calledNumbers]);
  const currentNumber = calledNumbers?.length ? Number(calledNumbers[calledNumbers.length - 1]) : null;
  const columns = useMemo(() => {
    const limit = Math.max(1, Number(maxNumber) || 400);
    const step = Math.floor(limit / 5);
    const letters = ["B", "I", "N", "G", "O"];

    return letters.map((letter, index) => {
      const start = index * step + 1;
      const end = index === 4 ? limit : (index + 1) * step;
      const numbers = Array.from({ length: end - start + 1 }, (_, offset) => start + offset);
      return { letter, numbers };
    });
  }, [maxNumber]);

  const handleNumberClick = (num) => {
    if (interactive && num === currentNumber && onNumberClick) {
      onNumberClick(num);
    }
  };

  return (
    <section className="component" id="calledNumbersComponent">
      <div className="component-title">Called Numbers</div>
      <div className="called-board">
        {columns.map((column) => (
          <div key={column.letter} className="called-column">
            <div className="called-col-head" data-letter={column.letter}>{column.letter}</div>
            <div className="called-col-grid">
              {column.numbers.map((num) => {
                const isCalled = calledSet.has(num);
                const isCurrent = num === currentNumber;
                const isClickable = interactive && isCurrent;
                
                return (
                  <div
                    key={num}
                    className={`called-cell${isCalled ? " called" : ""}${isCurrent ? " current" : ""}${isClickable ? " clickable" : ""}`}
                    onClick={() => handleNumberClick(num)}
                    style={{ cursor: isClickable ? 'pointer' : 'default' }}
                    title={isClickable ? `Click to mark ${num} on your card` : ''}
                  >
                    {num}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
