import type { MetadataRoute } from "next";

/**
 * Served as /robots.txt. The Atlas publishes public data only, so every crawler may read
 * every page.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
  };
}
