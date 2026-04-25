// API_INTERNAL_BASE is only available server-side (no PUBLIC_ prefix).
// It points at the Docker service name so SSR fetches work inside the container.
// Browser <script> tags fall back to PUBLIC_API_BASE (= localhost:8000).
export const API_BASE =
    import.meta.env.API_INTERNAL_BASE ??
    import.meta.env.PUBLIC_API_BASE ??
    "http://localhost:8000/api/v1";

export type SearchHit = {
    distro: string;
    release: string;
    package_name: string;
    version: string;
    description: string | null;
};

export async function search(q: string): Promise<SearchHit[]> {
    const r = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`);
    if (!r.ok) return [];
    const data = await r.json();
    return data.results ?? [];
}
