const TOKEN_KEY = "nestswipe_token";

export function photoUrl(s3Key: string): string {
  const token = localStorage.getItem(TOKEN_KEY) ?? "";
  return `/api/v1/photos/${s3Key}?token=${encodeURIComponent(token)}`;
}
