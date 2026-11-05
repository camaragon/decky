/** Extract owner/repo slug from a GitHub pull URL. */
export function repoSlugFromUrl(url: string): string | null {
  const match = url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+)\/pull\/\d+/i);
  return match ? match[1] : null;
}

export function queueItemRepo(item: { url: string; repo: string }): string {
  return repoSlugFromUrl(item.url) ?? item.repo;
}
