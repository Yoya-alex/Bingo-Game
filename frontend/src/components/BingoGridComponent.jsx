import { useEffect, useMemo, useRef } from "react";

export default function BingoGridComponent({ grid, calledNumbers }) {
  const gridRef = useRef(null);
  const cellMapRef = useRef(new Map());

  const flatGrid = useMemo(() => grid.flat(), [grid]);

  useEffect(() => {
    cellMapRef.current.clear();
    const cells = gridRef.current?.querySelectorAll(".bingo-cell[data-number]") || [];
    cells.forEach((cell) => {
      const value = Number(cell.dataset.number);
      if (!Number.isNaN(value)) {
        cellMapRef.current.set(value, cell);
      }
    });
  }, [flatGrid]);

  useEffect(() => {
    calledNumbers.forEach((num) => {
      const cell = cellMapRef.current.get(num);
      if (cell && !cell.classList.contains("marked")) {
        cell.classList.add("marked");
      }
    });
  }, [calledNumbers]);

  return (
    <section className="component" id="bingoGridComponent">
      <div className="component-title">Your Bingo Grid</div>
      <div className="bingo-grid" ref={gridRef}>
        {grid.map((row, rowIndex) =>
          row.map((cell, cellIndex) => (
            <div
              key={`${rowIndex}-${cellIndex}`}
              className={`bingo-cell${cell === null ? " free" : ""}`}
              data-number={cell ?? undefined}>
              {cell === null ? "FREE" : cell}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
