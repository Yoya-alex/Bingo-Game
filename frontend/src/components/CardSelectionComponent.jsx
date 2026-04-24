import { memo } from "react";
import { useI18n } from "../i18n/LanguageContext.jsx";

const CardChip = memo(function CardChip({ number, isTaken, isSelected, onSelect, t }) {
  const className = `card-chip${isTaken ? " taken" : ""}${isSelected ? " selected" : ""}`;
  return (
    <div
      className={className}
      title={isTaken ? t("cardSelection.taken") : isSelected ? t("cardSelection.selected") : t("cardSelection.selectCard")}
      onClick={() => !isTaken && onSelect(number)}>
      {number}
    </div>
  );
});

export default function CardSelectionComponent({ numbers, takenSet, selectedNumber, onSelect }) {
  const { t } = useI18n();

  return (
    <section className="component" id="cardSelectionComponent">
      <div className="component-title card-selection-title">{t("cardSelection.selectYourCard")}</div>
      <div className="card-grid" id="cardsGrid">
        {numbers.map((num) => (
          <CardChip
            key={num}
            number={num}
            isTaken={takenSet.has(num)}
            isSelected={selectedNumber === num}
            onSelect={onSelect}
            t={t}
          />
        ))}
      </div>
      <p className="subtitle" style={{ marginTop: "10px" }}>
        {t("cardSelection.tapAnyAvailable")}
      </p>
    </section>
  );
}
