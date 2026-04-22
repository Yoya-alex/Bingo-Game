import { useMemo } from "react";
import { useI18n } from "../i18n/LanguageContext.jsx";

export default function CalledNumbersComponent({ calledNumbers, maxNumber = 400, onNumberClick, interactive = true }) {
  const { t } = useI18n();
  const calledSet = useMemo(() => new Set(calledNumbers || []), [calledNumbers]);
  const currentNumber = calledNumbers?.length ? Number(calledNumbers[calledNumbers.length - 1]) : null;
  const currentCallParts = useMemo(() => {
    if (!Number.isFinite(currentNumber)) {
      return null;
    }

    const limit = Math.max(5, Number(maxNumber) || 400);
    const step = Math.max(1, Math.floor(limit / 5));
    const letters = ["B", "I", "N", "G", "O"];
    const index = Math.min(4, Math.max(0, Math.floor((currentNumber - 1) / step)));
    return {
      letter: letters[index],
      number: currentNumber,
    };
  }, [currentNumber, maxNumber]);

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
    if (interactive && calledSet.has(num) && onNumberClick) {
      onNumberClick(num);
    }
  };

  return (
    <section className="component" id="calledNumbersComponent">
      <div className="component-title">{t("calledNumbers.title")}</div>
      <div className="stat-strip current-call called-current-strip">
        <div className="stat-item current-call-item">
          <span className="current-call-label">{t("common.currentCall")}</span>
          <div className="stat-value current-call-value">
            {currentCallParts ? (
              <span className="call-badge">
                <span className="call-letter">{currentCallParts.letter}</span>
                <span className="call-value">{currentCallParts.number}</span>
              </span>
            ) : (
              "-"
            )}
          </div>
        </div>
      </div>
      <div className="called-board">
        {columns.map((column) => (
          <div key={column.letter} className="called-column">
            <div className="called-col-head" data-letter={column.letter}>{column.letter}</div>
            <div className="called-col-grid">
              {column.numbers.map((num) => {
                const isCalled = calledSet.has(num);
                const isCurrent = num === currentNumber;
                const isClickable = interactive && isCalled;
                
                return (
                  <div
                    key={num}
                    className={`called-cell${isCalled ? " called" : ""}${isCurrent ? " current" : ""}${isClickable ? " clickable" : ""}`}
                    onClick={() => handleNumberClick(num)}
                    style={{ cursor: isClickable ? 'pointer' : 'default' }}
                    title={isClickable ? t("calledNumbers.calledClickToMark", { number: num }) : ""}
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
