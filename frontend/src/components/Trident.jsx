// The TRISHUL-Q trident motif ("teen shool" = three prongs = three detection layers).
export default function Trident({ size = 34, color = "#5b6cff" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-label="TRISHUL-Q trident">
      <rect width="64" height="64" rx="14" fill="#0b1020" stroke="#26305a" />
      <g stroke={color} strokeWidth="3.4" strokeLinecap="round" fill="none">
        <path d="M20 16v16" />
        <path d="M32 12v20" />
        <path d="M44 16v16" />
        <path d="M32 30v18" />
        <path d="M20 32c0 6 5 10 12 10s12-4 12-10" />
      </g>
    </svg>
  );
}
