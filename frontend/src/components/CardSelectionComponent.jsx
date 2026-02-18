import { memo } from "react";

const CardChip = memo(function CardChip({ number, isTaken, isSelected, onSelect }) {
  const className = `card-chip${isTaken ? " taken" : ""}${isSelected ? " selected" : ""}`;
  return (
    <div
      className={className}
      title={isTaken ? "Taken" : isSelected ? "Selected" : "Select card"}
      onClick={() => !isTaken && onSelect(number)}>
      {number}
    </div>
  );
});

export default function CardSelectionComponent({ numbers, takenSet, selectedNumber, onSelect }) {
  return (
    <section className="component" id="cardSelectionComponent">
      <div className="component-title">Select Your Card</div>
      <div className="card-grid" id="cardsGrid">
        {numbers.map((num) => (
          <CardChip
            key={num}
            number={num}
            isTaken={takenSet.has(num)}
            isSelected={selectedNumber === num}
            onSelect={onSelect}
          />
        ))}
      </div>
      <p className="subtitle" style={{ marginTop: "10px" }}>
        Tap any available card to join.
      </p>
    </section>
  );
}
