export function documentSourceHref(
  documentId: string,
  options?: { page?: number | null; highlight?: string | null },
): string {
  const params = new URLSearchParams();
  if (options?.page != null && options.page > 0) {
    params.set("page", String(options.page));
  }
  if (options?.highlight?.trim()) {
    params.set("highlight", options.highlight.trim());
  }
  const q = params.toString();
  return q ? `/documents/${documentId}?${q}` : `/documents/${documentId}`;
}
