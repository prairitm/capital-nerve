export function documentSourceHref(
  documentId: string,
  options?: {
    page?: number | null;
    highlight?: string | null;
    value?: string | number | null;
    context?: string | null;
  },
): string {
  const params = new URLSearchParams();
  if (options?.page != null && options.page > 0) {
    params.set("page", String(options.page));
  }
  if (options?.highlight?.trim()) {
    params.set("highlight", options.highlight.trim());
  }
  if (options?.value != null && String(options.value).trim()) {
    params.set("value", String(options.value).trim());
  }
  if (options?.context?.trim()) {
    params.set("context", options.context.trim());
  }
  const q = params.toString();
  return q ? `/documents/${documentId}?${q}` : `/documents/${documentId}`;
}
