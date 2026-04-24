interface Props {
  open?: boolean;
}

export function Chev({ open }: Props) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      style={{
        transition: "transform .18s",
        transform: open ? "rotate(90deg)" : "rotate(0)",
        color: "var(--rib-text2)",
      }}
    >
      <path
        d="M3 2l3 3-3 3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
