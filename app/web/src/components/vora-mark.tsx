export function VoraMark({
  size = 30,
  inverted = false,
}: {
  size?: number;
  inverted?: boolean;
}) {
  const face = inverted ? "#FFFFFF" : "#1D1D1F";
  const ink = inverted ? "#1D1D1F" : "#FFFFFF";
  return (
    <svg width={size} height={size} viewBox="0 0 240 240" aria-hidden="true">
      <rect x="16" y="16" width="208" height="208" rx="60" fill={face} />
      <rect x="80" y="78" width="22" height="42" rx="11" fill={ink} />
      <rect x="138" y="78" width="22" height="42" rx="11" fill={ink} />
      <rect x="96" y="152" width="12" height="16" rx="6" fill={ink} />
      <rect x="114" y="148" width="12" height="24" rx="6" fill={ink} />
      <rect x="132" y="152" width="12" height="16" rx="6" fill={ink} />
    </svg>
  );
}
