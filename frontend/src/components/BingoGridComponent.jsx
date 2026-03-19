import { useMemo } from "react";

export default function BingoGridComponent({
  grid,
  calledNumbers = [],
  markedNumbers = [],
  markSource = "called",
  clickableNumber = null,
  onSelectNumber,
  title = "Your Bingo Grid",
  id = "bingoGridComponent",
  interactive = false,
  footer = null,
}) {
  const flatGrid = useMemo(() => grid.flat(), [grid]);
  const calledSet = useMemo(() => new Set(calledNumbers), [calledNumbers]);
  const markedSet = useMemo(() => new Set(markedNumbers), [markedNumbers]);

  function handleSelect(value, canSelect) {
    if (!canSelect || typeof onSelectNumber !== "function") {
      return;
    }
    onSelectNumber(value);
  }

  return (
    <section className="component" id={id}>
      <div className="component-title">{title}</div>
      <div className="bingo-columns" aria-hidden="true">
        <span className="bingo-col" data-letter="B">B</span>
        <span className="bingo-col" data-letter="I">I</span>
        <span className="bingo-col" data-letter="N">N</span>
        <span className="bingo-col" data-letter="G">G</span>
        <span className="bingo-col" data-letter="O">O</span>
      </div>
      <div className="bingo-grid">
        {flatGrid.map((cell, index) => {
          const isFree = cell === null;
          const isMarked = isFree || (markSource === "marked" ? markedSet.has(cell) : calledSet.has(cell));

          const canSelect =
            interactive &&
            markSource === "marked" &&
            !isFree &&
            calledSet.has(cell) &&  // Allow clicking any called number
            !markedSet.has(cell);

          return (
            <div
              key={index}
              className={`bingo-cell${isFree ? " free" : ""}${isMarked && !isFree ? " marked" : ""}${canSelect ? " clickable" : ""}`}
              clickable={canSelect ? "true" : "false"}
              data-clickable={canSelect ? "true" : "false"}
              onClick={canSelect ? () => handleSelect(cell, canSelect) : undefined}
              style={{ cursor: canSelect ? 'pointer' : 'default' }}
              title={canSelect ? `Click to mark ${cell}` : ''}>
              {isFree ? "FREE" : cell}
            </div>
          );
        })}
      </div>
      {footer && <div className="bingo-footer">{footer}</div>}
    </section>
  );
}
