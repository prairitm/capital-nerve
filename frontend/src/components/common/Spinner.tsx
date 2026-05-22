export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-ink-mute border-t-transparent"
      style={{ width: size, height: size }}
    />
  );
}

export function PageLoader() {
  return (
    <div className="flex items-center justify-center py-24 text-ink-mute gap-3 text-sm">
      <Spinner size={18} />
      Loading…
    </div>
  );
}
